"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronRight, Loader2, Play, RotateCcw } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { ErrorState } from "@/components/common/error-state";
import { PageHeader } from "@/components/common/page-header";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi } from "@/lib/query";
import { cn } from "@/lib/utils";

interface Step {
  n: number;
  key: string;
  actor: string;
  done: boolean;
  done_at?: string;
  result?: Record<string, unknown>;
  links?: { label: string; href: string }[];
}

function Value({ v }: { v: unknown }) {
  if (Array.isArray(v)) {
    return (
      <ul className="grid gap-0.5">
        {v.map((x, i) => (
          <li key={i}>{typeof x === "object" && x ? Object.values(x as Record<string, unknown>).slice(0, 2).map(String).join(": ") : String(x)}</li>
        ))}
      </ul>
    );
  }
  return <>{v === null ? "—" : String(v)}</>;
}

export default function DemoPage() {
  const { t } = useT();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const data = useApi<{ steps: Step[] }>("/demo/walkthrough");
  const run = useMutation({
    mutationFn: (n: number) => api<Step>(`/demo/walkthrough/${n}`, { method: "POST" }),
    onSuccess: (s) => {
      toast.success(t("demo.stepDone", { n: s.n }));
      qc.invalidateQueries();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (data.error) return <ErrorState error={data.error} onRetry={() => data.refetch()} />;
  const steps = data.data?.steps;
  const done = steps?.filter((s) => s.done).length ?? 0;
  const next = steps?.find((s) => !s.done);
  // Evaluators are read-only elsewhere but may drive the demo; the API enforces demo mode and roles.
  const canRun = hasRole(user, "evaluator", "gp_admin", "mrf_operator");

  return (
    <>
      <PageHeader title={t("nav.items.demo")} description={t("demo.subtitle")}
        actions={canRun && (
          <ConfirmDialog trigger={<Button variant="outline"><RotateCcw /> {t("demo.reset")}</Button>} title={t("demo.reset")} description={t("demo.resetHint")}
            onConfirm={async () => { await api("/demo/walkthrough/reset", { method: "POST" }); qc.invalidateQueries(); }} />
        )} />
      <Alert tone="warning" className="mb-4">{t("demo.notice")}</Alert>
      {!steps ? <Skeleton className="h-96" /> : (
        <>
          <div className="mb-6 flex items-center gap-3">
            <Progress value={(done / steps.length) * 100} className="h-2 flex-1" />
            <span className="tabular text-sm text-muted-foreground">{done}/{steps.length}</span>
          </div>
          <ol className="grid gap-3">
            {steps.map((s) => {
              const isNext = next?.n === s.n;
              return (
                <li key={s.n}>
                  <Card className={cn(isNext && "border-primary ring-1 ring-primary")}>
                    <CardContent className="grid gap-3 pt-5 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-start">
                      <span className={cn("grid size-9 place-items-center rounded-full text-sm font-semibold", s.done ? "bg-primary text-primary-foreground" : "bg-muted")}>
                        {s.done ? <CheckCircle2 className="size-5" /> : s.n}
                      </span>
                      <div className="min-w-0">
                        <p className="font-semibold">{t(`demo.steps.${s.key}.title`)}</p>
                        <p className="text-sm text-muted-foreground">{t(`demo.steps.${s.key}.desc`)}</p>
                        <p className="mt-1 text-xs"><Badge tone="neutral">{t("demo.as", { who: t(`demo.actors.${s.actor}`) })}</Badge></p>
                        {s.result && (
                          <dl className="mt-3 grid gap-1 rounded-lg bg-muted/60 p-3 text-xs sm:grid-cols-2">
                            {Object.entries(s.result).map(([k, v]) => (
                              <div key={k} className="flex gap-2">
                                <dt className="text-muted-foreground">{k.replace(/_/g, " ")}:</dt>
                                <dd className="min-w-0 font-medium"><Value v={v} /></dd>
                              </div>
                            ))}
                          </dl>
                        )}
                        {s.links && s.links.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-3 text-sm">
                            {s.links.map((l) => (
                              <Link key={l.href} href={l.href} className="inline-flex items-center text-primary hover:underline">
                                {t(`demo.links.${l.label}`)} <ChevronRight className="size-4" />
                              </Link>
                            ))}
                          </div>
                        )}
                      </div>
                      {canRun && !s.done && (
                        <Button disabled={!isNext || run.isPending} onClick={() => run.mutate(s.n)}>
                          {run.isPending && run.variables === s.n ? <Loader2 className="animate-spin" /> : <Play />} {t("demo.run")}
                        </Button>
                      )}
                    </CardContent>
                  </Card>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </>
  );
}
