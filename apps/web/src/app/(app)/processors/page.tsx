"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, FileCheck2, Plus, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Field } from "@/components/common/field";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi } from "@/lib/query";
import type { MaterialCategory, Partner } from "@/lib/types";
import { cn, formatKg } from "@/lib/utils";

function AddPartner({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t } = useT();
  const qc = useQueryClient();
  const categories = useApi<MaterialCategory[]>("/settings/material-categories");
  const [form, setForm] = useState({ display_name: "", capabilities: "", acceptance_criteria: "", contact_name: "", contact_phone: "" });
  const [cats, setCats] = useState<string[]>([]);
  const save = useMutation({
    mutationFn: () => api("/processors", { method: "POST", body: { ...form, contact_phone: form.contact_phone || null, supported_category_codes: cats } }),
    onSuccess: () => {
      toast.success(t("common.saved"));
      qc.invalidateQueries({ queryKey: ["/processors"] });
      onOpenChange(false);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>{t("processors.add")}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <Field label={t("common.name")} htmlFor="pp-name" required>
            <Input id="pp-name" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          </Field>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">{t("processors.accepts")}</legend>
            <div className="flex flex-wrap gap-1.5">
              {categories.data?.filter((c) => !c.is_unsorted).map((c) => (
                <button key={c.code} type="button" aria-pressed={cats.includes(c.code)}
                  onClick={() => setCats((xs) => (xs.includes(c.code) ? xs.filter((x) => x !== c.code) : [...xs, c.code]))}
                  className={cn("rounded-lg border px-3 py-1.5 text-sm", cats.includes(c.code) && "border-primary bg-secondary font-medium")}>
                  {c.label}
                </button>
              ))}
            </div>
          </fieldset>
          <Field label={t("processors.capabilities")} htmlFor="pp-cap">
            <Textarea id="pp-cap" value={form.capabilities} onChange={(e) => setForm({ ...form, capabilities: e.target.value })} />
          </Field>
          <Field label={t("processors.criteria")} htmlFor="pp-crit">
            <Textarea id="pp-crit" value={form.acceptance_criteria} onChange={(e) => setForm({ ...form, acceptance_criteria: e.target.value })} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("processors.contact")} htmlFor="pp-contact">
              <Input id="pp-contact" value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} />
            </Field>
            <Field label={t("common.phone")} htmlFor="pp-phone">
              <Input id="pp-phone" inputMode="tel" value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} />
            </Field>
          </div>
        </div>
        <DialogFooter>
          <Button disabled={form.display_name.trim().length < 3 || !cats.length || save.isPending} onClick={() => save.mutate()}>{t("common.save")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PartnerCard({ p }: { p: Partner }) {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const isOperator = hasRole(user, "mrf_operator");
  const isOwn = hasRole(user, "processor") && user?.memberships.some((m) => m.organization_id === p.organization_id);
  const refresh = () => qc.invalidateQueries({ queryKey: ["/processors"] });
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file, file.name);
      form.append("purpose", "processor_document");
      const media = await api<{ id: string }>("/media", { method: "POST", form });
      return api(`/processors/${p.id}/documents`, { method: "POST", body: { media_id: media.id, authorization_refs: [] } });
    },
    onSuccess: () => { toast.success(t("processors.docsSubmitted")); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const review = useMutation({
    mutationFn: (decision: "verify" | "reject") => api(`/processors/${p.id}/documents/review`, { method: "POST", body: { decision } }),
    onSuccess: () => { toast.success(t("common.saved")); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          {p.display_name}
          {p.is_sample && <OriginBadge origin="demo_seed" />}
        </CardTitle>
        <CardDescription>{p.capabilities}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        <div className="flex flex-wrap gap-1">
          {p.supported_category_codes.map((c) => <Badge key={c} tone="neutral">{t(`processors.cats.${c}`)}</Badge>)}
        </div>
        {p.acceptance_criteria && <p className="text-muted-foreground">{t("processors.criteria")}: {p.acceptance_criteria}</p>}
        <div className="grid grid-cols-3 gap-2">
          <div><p className="text-xs text-muted-foreground">{t("processors.transfers")}</p><p className="tabular font-semibold">{p.transfers}</p></div>
          <div><p className="text-xs text-muted-foreground">{t("processors.received")}</p><p className="tabular font-semibold">{formatKg(p.received_kg, locale)}</p></div>
          <div><p className="text-xs text-muted-foreground">{t("processors.recovered")}</p><p className="tabular font-semibold">{formatKg(p.recovered_reviewed_kg, locale)}</p></div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-muted-foreground">{t("processors.documents")}:</span>
          <StatusBadge value={p.documentation_status} />
          {p.documentation_url && <a className="text-primary underline" href={p.documentation_url} target="_blank" rel="noreferrer">{t("processors.view")}</a>}
        </div>
        {isOwn && (
          <label className="inline-flex cursor-pointer items-center gap-2 self-start rounded-md border px-3 py-1.5 text-sm hover:bg-muted">
            <Upload className="size-4" /> {t("processors.uploadDocs")}
            <input type="file" accept="application/pdf,image/*" className="sr-only" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} />
          </label>
        )}
        {isOperator && p.documentation_status === "submitted" && (
          <div className="flex gap-2">
            <Button size="sm" onClick={() => review.mutate("verify")} disabled={review.isPending}><FileCheck2 /> {t("processors.verifyDocs")}</Button>
            <Button size="sm" variant="outline" onClick={() => review.mutate("reject")} disabled={review.isPending}>{t("processors.rejectDocs")}</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function ProcessorsPage() {
  const { t } = useT();
  const user = useAuth((s) => s.user);
  const list = useApi<Partner[]>("/processors");
  const [open, setOpen] = useState(false);
  return (
    <>
      <PageHeader title={t("nav.items.processors")} description={t("processors.subtitle")}
        actions={hasRole(user, "mrf_operator") && <Button onClick={() => setOpen(true)}><Plus /> {t("processors.add")}</Button>} />
      <Alert tone="info" className="mb-4">{t("processors.notice")}</Alert>
      {list.error ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : !list.data ? (
        <Skeleton className="h-64" />
      ) : list.data.length === 0 ? (
        <EmptyState icon={Building2} title={t("processors.empty")} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">{list.data.map((p) => <PartnerCard key={p.id} p={p} />)}</div>
      )}
      {open && <AddPartner open={open} onOpenChange={setOpen} />}
    </>
  );
}
