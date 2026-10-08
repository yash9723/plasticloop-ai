"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BellOff, CheckCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { useApi, usePagedList } from "@/lib/query";
import type { NotificationItem } from "@/lib/types";
import { cn, relativeTime } from "@/lib/utils";

const tone = { info: "info", warning: "warning", critical: "danger" } as const;

function Preferences() {
  const { t } = useT();
  const types = useApi<string[]>("/notifications/types");
  const prefs = useApi<{ muted_types: string[] }>("/notifications/preferences");
  const [muted, setMuted] = useState<string[] | null>(null);
  useEffect(() => {
    if (prefs.data && muted === null) setMuted(prefs.data.muted_types); // eslint-disable-line react-hooks/set-state-in-effect
  }, [prefs.data, muted]);
  const save = useMutation({
    mutationFn: () => api("/notifications/preferences", { method: "PUT", body: { muted_types: muted ?? [] } }),
    onSuccess: () => toast.success(t("common.saved")),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("notifications.preferences")}</CardTitle>
          <CardDescription>{t("notifications.preferencesHint")}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="grid gap-2">
        {!types.data && <Skeleton className="h-40 w-full" />}
        {types.data?.map((ty) => (
          <label key={ty} className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm">
            <span>{t(`notifications.types.${ty}`)}</span>
            <span className="flex items-center gap-2 text-xs text-muted-foreground">
              {t("notifications.mute")}
              <Switch
                checked={muted?.includes(ty) ?? false}
                onCheckedChange={(v) => setMuted((m) => (v ? [...(m ?? []), ty] : (m ?? []).filter((x) => x !== ty)))}
              />
            </span>
          </label>
        ))}
        <Button className="mt-2 justify-self-start" onClick={() => save.mutate()} disabled={save.isPending || muted === null}>
          {t("notifications.savePreferences")}
        </Button>
      </CardContent>
    </Card>
  );
}

export default function NotificationsPage() {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const list = usePagedList<NotificationItem>("/notifications", { sort: "-created" });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["/notifications"] }).then(() => qc.invalidateQueries({ queryKey: ["notifications"] }));
  const markRead = useMutation({ mutationFn: (id: string) => api(`/notifications/${id}/read`, { method: "POST" }), onSuccess: invalidate });
  const readAll = useMutation({ mutationFn: () => api("/notifications/read-all", { method: "POST" }), onSuccess: invalidate });
  const unreadOnly = list.filters.unread_only === true;

  return (
    <>
      <PageHeader
        title={t("nav.items.notifications")}
        actions={
          <>
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={unreadOnly} onCheckedChange={(v) => list.setFilter("unread_only", v || undefined)} />
              {t("notifications.unreadOnly")}
            </label>
            <Button variant="outline" onClick={() => readAll.mutate()} disabled={readAll.isPending}>
              <CheckCheck /> {t("notifications.markAllRead")}
            </Button>
          </>
        }
      />
      <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
        <div>
          {list.isLoading && <Skeleton className="h-64 w-full" />}
          {list.data?.items.length === 0 && <EmptyState icon={BellOff} title={t("notifications.empty")} />}
          <ul className="grid gap-2">
            {list.data?.items.map((n) => (
              <li key={n.id} className={cn("flex items-start gap-3 rounded-xl border bg-card p-4", !n.read_at && "border-primary/30")}>
                <Badge tone={tone[n.severity]}>{t(`notifications.severity.${n.severity}`)}</Badge>
                <div className="min-w-0 flex-1">
                  <p className={cn("text-sm", !n.read_at && "font-semibold")}>
                    {n.link ? (
                      <Link href={n.link} className="hover:underline">
                        {n.title}
                      </Link>
                    ) : (
                      n.title
                    )}
                  </p>
                  {n.body && <p className="mt-0.5 text-sm text-muted-foreground">{n.body}</p>}
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t(`notifications.types.${n.type}`)} · {relativeTime(n.created_at, locale)}
                  </p>
                </div>
                {!n.read_at && (
                  <Button size="sm" variant="ghost" onClick={() => markRead.mutate(n.id)}>
                    {t("notifications.markRead")}
                  </Button>
                )}
              </li>
            ))}
          </ul>
          <Pagination page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPageChange={list.setPage} />
        </div>
        <Preferences />
      </div>
    </>
  );
}
