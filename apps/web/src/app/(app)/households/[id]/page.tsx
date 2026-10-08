"use client";

import { ShieldAlert, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { ErrorState } from "@/components/common/error-state";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n/i18n";
import { api } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi } from "@/lib/query";
import type { CollectionEvent, Household, PickupRequest } from "@/lib/types";
import { formatDate, formatDateTime, formatKg } from "@/lib/utils";

interface HouseholdDetail {
  household: Household;
  village_name: string | null;
  collection_point_ids: string[];
  recent_collections: CollectionEvent[];
  pickup_requests: PickupRequest[];
  open_complaints: number;
}

export default function HouseholdDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useT();
  const router = useRouter();
  const user = useAuth((s) => s.user);
  const d = useApi<HouseholdDetail>(`/households/${id}`);
  if (d.error) return <ErrorState error={d.error} onRetry={() => d.refetch()} />;
  if (!d.data) return <Skeleton className="h-96 w-full" />;
  const h = d.data.household;
  return (
    <>
      <PageHeader
        title={h.head_name}
        description={`${h.household_code} · ${d.data.village_name ?? ""}`}
        eyebrow={
          <>
            <StatusBadge value={h.active ? "active" : "inactive"} />
            {h.is_sample && <OriginBadge origin="demo_seed" />}
          </>
        }
        actions={
          hasRole(user, "gp_admin") && (
            <ConfirmDialog
              trigger={
                <Button variant="outline" className="text-danger-foreground">
                  <Trash2 /> {t("households.erase")}
                </Button>
              }
              title={t("households.eraseTitle")}
              description={t("households.eraseBody")}
              destructive
              confirmLabel={t("households.erase")}
              onConfirm={async () => {
                await api(`/households/${id}`, { method: "DELETE" });
                router.replace("/households");
              }}
            />
          )
        }
      />
      {h.redacted && (
        <Alert tone="info" className="mb-5">
          <ShieldAlert />
          <AlertDescription>{t("households.redacted")}</AlertDescription>
        </Alert>
      )}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>{t("common.details")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm">
            <p>
              <span className="text-muted-foreground">{t("common.phone")}:</span> {h.phone ?? "—"}
            </p>
            <p>
              <span className="text-muted-foreground">{t("common.address")}:</span> {h.address_line ?? "—"}
            </p>
            <p>
              <span className="text-muted-foreground">{t("households.members")}:</span> {h.members_count ?? "—"}
            </p>
            <p>
              <span className="text-muted-foreground">{t("households.account")}:</span> {h.has_account ? t("common.yes") : t("common.no")}
            </p>
            <p>
              <span className="text-muted-foreground">{t("households.openComplaints")}:</span> {d.data.open_complaints}
            </p>
            {d.data.collection_point_ids.map((cp) => (
              <Link key={cp} href={`/collection-points/${cp}`} className="text-primary hover:underline">
                {t("households.viewPoint")}
              </Link>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("nav.items.pickupRequests")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            {d.data.pickup_requests.length === 0 && <p className="text-sm text-muted-foreground">{t("common.noData")}</p>}
            {d.data.pickup_requests.map((r) => (
              <div key={r.id} className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
                <span>{formatDate(r.preferred_date ?? r.created_at, locale)}</span>
                <StatusBadge value={r.status} />
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("dashboard.household.history")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            {d.data.recent_collections.length === 0 && <p className="text-sm text-muted-foreground">{t("common.noData")}</p>}
            {d.data.recent_collections.map((c) => (
              <div key={c.id} className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
                <span>{formatDateTime(c.collected_at, locale)}</span>
                <span className="tabular font-medium">{formatKg(c.weight_kg, locale)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
