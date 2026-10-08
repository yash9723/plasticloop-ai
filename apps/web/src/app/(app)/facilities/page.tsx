"use client";

import { Factory, PackageCheck } from "lucide-react";
import Link from "next/link";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n/i18n";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi } from "@/lib/query";
import type { Facility } from "@/lib/types";
import { formatKg } from "@/lib/utils";

export default function FacilitiesPage() {
  const { t, locale } = useT();
  const user = useAuth((s) => s.user);
  const list = useApi<Facility[]>("/facilities");
  return (
    <>
      <PageHeader title={t("nav.items.facilities")} description={t("facilities.subtitle")}
        actions={hasRole(user, "mrf_operator") && (
          <Button asChild>
            <Link href="/facilities/intake">
              <PackageCheck /> {t("nav.items.intake")}
            </Link>
          </Button>
        )} />
      {list.error ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : !list.data ? (
        <div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-44" /><Skeleton className="h-44" /></div>
      ) : list.data.length === 0 ? (
        <EmptyState icon={Factory} title={t("facilities.empty")} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {list.data.map((f) => (
            <Link key={f.id} href={`/facilities/${f.id}`} className="rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
              <Card className="h-full transition-colors hover:border-primary/50">
                <CardHeader>
                  <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                    {f.name}
                    {f.is_sample && <OriginBadge origin="demo_seed" />}
                  </CardTitle>
                  <CardDescription>
                    {f.code} · {t(`facilities.types.${f.facility_type}`)}
                  </CardDescription>
                </CardHeader>
                <CardContent className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <p className="text-xs text-muted-foreground">{t("facilities.stock")}</p>
                    <p className="tabular text-xl font-semibold">{formatKg(f.stock_kg, locale)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">{t("facilities.activeBatches")}</p>
                    <p className="tabular text-xl font-semibold">{f.active_batches}</p>
                  </div>
                  <p className="col-span-2 text-xs text-muted-foreground">
                    {t("facilities.serves")}: {f.village_names.join(", ") || "—"}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
