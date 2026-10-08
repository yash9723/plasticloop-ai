"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { localized, useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth-store";
import { useApi } from "@/lib/query";
import type { MaterialCategory, SystemSettingItem, WasteStream } from "@/lib/types";

function SystemSettings({ editable }: { editable: boolean }) {
  const { t } = useT();
  const qc = useQueryClient();
  const settings = useApi<SystemSettingItem[]>("/settings/system");
  const [draft, setDraft] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: () => api("/settings/system", { method: "PATCH", body: Object.fromEntries(Object.entries(draft).map(([k, v]) => [k, Number(v)])) }),
    onSuccess: () => {
      toast.success(t("common.saved"));
      setDraft({});
      qc.invalidateQueries({ queryKey: ["/settings/system"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!settings.data) return <Skeleton className="h-96 w-full" />;
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("settings.thresholds")}</CardTitle>
          <CardDescription>{t("settings.thresholdsHint")}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="grid gap-2">
        {settings.data.map((s) => (
          <div key={s.key} className="grid items-center gap-2 rounded-lg border px-3 py-2 sm:grid-cols-[1fr_9rem]">
            <div>
              <p className="text-sm font-medium">{s.description}</p>
              <p className="font-mono text-[11px] text-muted-foreground">
                {s.key} · {t("settings.default")}: {String(s.default)}
              </p>
            </div>
            <Input
              inputMode="decimal"
              aria-label={s.key}
              disabled={!editable}
              value={draft[s.key] ?? String(s.value)}
              onChange={(e) => setDraft({ ...draft, [s.key]: e.target.value })}
            />
          </div>
        ))}
        {editable && (
          <Button className="mt-2 justify-self-start" onClick={() => save.mutate()} disabled={!Object.keys(draft).length || save.isPending}>
            {t("common.save")}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function Streams({ editable }: { editable: boolean }) {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const streams = useApi<WasteStream[]>("/settings/waste-streams", { include_inactive: true });
  const toggle = useMutation({
    mutationFn: (s: WasteStream) => api(`/settings/waste-streams/${s.id}`, { method: "PATCH", body: { active: !s.active } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["/settings/waste-streams"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("settings.streams")}</CardTitle>
          <CardDescription>{t("settings.streamsHint")}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3">
        {streams.data?.map((s) => (
          <div key={s.id} className="flex items-start gap-3 rounded-lg border p-3">
            <span className="mt-1 size-3 shrink-0 rounded-full" style={{ background: s.color }} aria-hidden />
            <div className="min-w-0 flex-1 text-sm">
              <p className="font-medium">
                {localized(s.labels, s.label, locale)} <span className="font-mono text-xs text-muted-foreground">{s.code}</span>
              </p>
              <p className="text-muted-foreground">{s.description}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                EN: {s.label} · HI: {String(s.labels.hi ?? "—")} · TE: {String(s.labels.te ?? "—")}
              </p>
              {s.is_demo_config && (
                <Badge tone="info" className="mt-1.5">
                  {t("settings.demoConfig")}
                </Badge>
              )}
            </div>
            <Switch checked={s.active} disabled={!editable} onCheckedChange={() => toggle.mutate(s)} aria-label={t("status.active")} />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function Categories() {
  const { t, locale } = useT();
  const cats = useApi<MaterialCategory[]>("/settings/material-categories");
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("settings.categories")}</CardTitle>
          <CardDescription>{t("settings.categoriesHint")}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="grid gap-2">
        {cats.data?.map((c) => (
          <div key={c.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm">
            <span>
              {localized(c.labels, c.label, locale)} <span className="font-mono text-xs text-muted-foreground">{c.code}</span>
            </span>
            <span className="flex flex-wrap gap-1">
              {c.is_mlp && <Badge tone="warning">MLP</Badge>}
              {c.requires_evidence_for_verification && <Badge tone="info">{t("settings.needsEvidence")}</Badge>}
              <StatusBadge value={c.recoverable ? "active" : "inactive"} />
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { t } = useT();
  const user = useAuth((s) => s.user);
  const editable = !!user?.roles.includes("super_admin");
  return (
    <>
      <PageHeader title={t("nav.items.settings")} description={t("settings.subtitle")} />
      {!editable && (
        <Alert tone="neutral" className="mb-5">
          <AlertDescription>{t("settings.readOnly")}</AlertDescription>
        </Alert>
      )}
      <Tabs defaultValue="system">
        <TabsList>
          <TabsTrigger value="system">{t("settings.thresholds")}</TabsTrigger>
          <TabsTrigger value="streams">{t("settings.streams")}</TabsTrigger>
          <TabsTrigger value="categories">{t("settings.categories")}</TabsTrigger>
        </TabsList>
        <TabsContent value="system">
          <SystemSettings editable={editable} />
        </TabsContent>
        <TabsContent value="streams">
          <Streams editable={editable} />
        </TabsContent>
        <TabsContent value="categories">
          <Categories />
        </TabsContent>
      </Tabs>
    </>
  );
}
