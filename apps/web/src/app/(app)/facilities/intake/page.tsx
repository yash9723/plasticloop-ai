"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, PackageCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Field } from "@/components/common/field";
import { PageHeader } from "@/components/common/page-header";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/query";
import type { Facility, Intake } from "@/lib/types";
import { formatKg } from "@/lib/utils";

const KG_RE = /^\d{1,5}(\.\d{1,3})?$/;
const EMPTY = { village: "", transporter: "", gross: "", tare: "", declared: "", storage: "", notes: "" };

export default function IntakePage() {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const facilities = useApi<Facility[]>("/facilities");
  const [facilityId, setFacilityId] = useState<string | null>(null);
  const fid = facilityId ?? facilities.data?.[0]?.id ?? "";
  const facility = facilities.data?.find((f) => f.id === fid);
  const villages = useApi<{ id: string; name: string }[]>(fid ? `/facilities/${fid}/villages` : null);
  const [form, setForm] = useState(EMPTY);
  const [done, setDone] = useState<Intake | null>(null);
  const set = (k: keyof typeof EMPTY, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const gross = Number(form.gross);
  const tare = Number(form.tare || 0);
  const net = KG_RE.test(form.gross) && (form.tare === "" || KG_RE.test(form.tare)) ? gross - tare : NaN;
  const valid = Number.isFinite(net) && net > 0 && (form.declared === "" || KG_RE.test(form.declared));
  const gap = form.declared && valid ? Number(form.declared) - net : null;

  const save = useMutation({
    mutationFn: () =>
      api<Intake>(`/facilities/${fid}/intakes`, {
        method: "POST",
        body: {
          gross_kg: form.gross, tare_kg: form.tare || "0", origin_village_id: form.village || null, transporter_name: form.transporter || null,
          declared_collected_kg: form.declared || null, storage_location: form.storage || null, notes: form.notes || null,
        },
      }),
    onSuccess: (r) => {
      setDone(r);
      setForm(EMPTY);
      qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/facilities") || String(q.queryKey[0]).startsWith("/inventory") });
      toast.success(t("intake.saved", { code: r.code }));
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <PageHeader title={t("nav.items.intake")} description={t("intake.subtitle")} />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,340px)]">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <PackageCheck className="size-4" /> {t("intake.weighIn")}
            </CardTitle>
            <CardDescription>{t("intake.weighHint")}</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); if (valid) save.mutate(); }}>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={t("common.facility")} htmlFor="in-fac" required>
                  <Select id="in-fac" value={fid} onChange={(e) => setFacilityId(e.target.value)}>
                    {facilities.data?.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label={t("intake.fromVillage")} htmlFor="in-village">
                  <Select id="in-village" value={form.village} onChange={(e) => set("village", e.target.value)}>
                    <option value="">{t("intake.otherSource")}</option>
                    {villages.data?.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              <Field label={t("intake.transporter")} htmlFor="in-transporter" hint={t("intake.transporterHint")}>
                <Input id="in-transporter" value={form.transporter} onChange={(e) => set("transporter", e.target.value)} />
              </Field>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label={t("intake.gross")} htmlFor="in-gross" required error={form.gross && !KG_RE.test(form.gross) ? t("validation.weight") : undefined}>
                  <Input id="in-gross" inputMode="decimal" value={form.gross} onChange={(e) => set("gross", e.target.value)} className="text-lg tabular" />
                </Field>
                <Field label={t("intake.tare")} htmlFor="in-tare" hint={t("intake.tareHint")}>
                  <Input id="in-tare" inputMode="decimal" value={form.tare} onChange={(e) => set("tare", e.target.value)} className="text-lg tabular" />
                </Field>
                <div className="grid content-end">
                  <p className="text-xs text-muted-foreground">{t("intake.net")}</p>
                  <p className="tabular text-2xl font-semibold" aria-live="polite">{Number.isFinite(net) && net > 0 ? formatKg(net, locale) : "—"}</p>
                </div>
              </div>
              {Number.isFinite(net) && net <= 0 && <Alert tone="danger">{t("intake.tareTooHigh")}</Alert>}
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={t("intake.declared")} htmlFor="in-declared" hint={t("intake.declaredHint")}>
                  <Input id="in-declared" inputMode="decimal" value={form.declared} onChange={(e) => set("declared", e.target.value)} />
                </Field>
                <Field label={t("intake.storage")} htmlFor="in-storage">
                  <Select id="in-storage" value={form.storage} onChange={(e) => set("storage", e.target.value)}>
                    <option value="">—</option>
                    {(facility?.storage_locations as string[] | undefined)?.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              {gap !== null && Math.abs(gap) > 0.5 && (
                <p className="text-sm text-muted-foreground">{t("intake.gapNote", { gap: formatKg(gap, locale) })}</p>
              )}
              <Field label={t("common.notes")} htmlFor="in-notes">
                <Textarea id="in-notes" value={form.notes} onChange={(e) => set("notes", e.target.value)} />
              </Field>
              <Button type="submit" size="lg" disabled={!valid || !fid || save.isPending}>
                {t("intake.record")}
              </Button>
            </form>
          </CardContent>
        </Card>
        <div className="grid content-start gap-4">
          {done && (
            <Card className="border-primary/40">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base text-primary">
                  <CheckCircle2 className="size-5" /> {t("intake.recorded")}
                </CardTitle>
                <CardDescription>{done.code}</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 text-sm">
                <p>{t("intake.recordedBody", { net: formatKg(done.net_kg, locale), batch: done.batch_code ?? "" })}</p>
                {done.batch_id && (
                  <Button asChild>
                    <Link href={`/inventory/${done.batch_id}`}>{t("intake.sortNow")}</Link>
                  </Button>
                )}
              </CardContent>
            </Card>
          )}
          <Alert tone="info">{t("intake.honesty")}</Alert>
        </div>
      </div>
    </>
  );
}
