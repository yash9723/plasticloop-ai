"use client";

import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { CollectionForm } from "@/components/collector/collection-form";
import { Field } from "@/components/common/field";
import { PageHeader } from "@/components/common/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { useT } from "@/i18n/i18n";
import type { Page } from "@/lib/api";
import { useLabels } from "@/lib/lookups";
import { useApi } from "@/lib/query";
import type { CollectionPoint } from "@/lib/types";

/** Desktop entry form. Uses the same offline queue + idempotent sync as the collector app. */
export default function NewCollectionPage() {
  const { t } = useT();
  const labels = useLabels();
  const [villageId, setVillageId] = useState("");
  const [pointId, setPointId] = useState("");
  const [formKey, setFormKey] = useState(0);
  const points = useApi<Page<CollectionPoint>>(villageId ? "/collection-points" : null, { village_id: villageId, status: "active", page_size: 200 });
  const point = points.data?.items.find((p) => p.id === pointId);

  return (
    <>
      <PageHeader title={t("command.newCollection")} description={t("collections.newSubtitle")} />
      <Card className="max-w-2xl">
        <CardContent className="grid gap-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("common.village")} htmlFor="village">
              <Select id="village" value={villageId} onChange={(e) => {
                setVillageId(e.target.value);
                setPointId("");
              }}>
                <option value="">{t("auth.selectVillage")}</option>
                {labels.villages.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t("collections.point")} htmlFor="point">
              <Select id="point" value={pointId} onChange={(e) => setPointId(e.target.value)} disabled={!villageId}>
                <option value="">{t("collections.selectPoint")}</option>
                {points.data?.items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.code} · {p.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          {point && (
            <CollectionForm
              key={`${point.id}-${formKey}`}
              point={{ id: point.id, code: point.code, name: point.name, stream_ids: point.stream_ids, device_id: point.device?.device_id }}
              streams={labels.streams}
              onSaved={() => {
                toast.success(t("collector.saved"));
                setFormKey((k) => k + 1);
              }}
            />
          )}
          <p className="text-sm text-muted-foreground">
            {t("collections.queueNote")}{" "}
            <Link href="/collector/offline-queue" className="text-primary hover:underline">
              {t("nav.items.offlineQueue")}
            </Link>
          </p>
        </CardContent>
      </Card>
    </>
  );
}
