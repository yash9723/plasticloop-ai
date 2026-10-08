"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Store } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { EmptyState } from "@/components/common/empty-state";
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
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n/i18n";
import { api, errorMessage, type Page } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi } from "@/lib/query";
import type { Batch, Listing } from "@/lib/types";
import { formatINR, formatKg } from "@/lib/utils";

const invalidate = (qc: ReturnType<typeof useQueryClient>) =>
  qc.invalidateQueries({ predicate: (q) => ["/marketplace", "/inventory", "/finance"].some((p) => String(q.queryKey[0]).startsWith(p)) });

function NewListing({ onClose }: { onClose: () => void }) {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const batches = useApi<Page<Batch>>("/inventory/batches", { status: "active", page_size: 200 });
  const [form, setForm] = useState({ batch_id: "", kg: "", price: "", notes: "" });
  const save = useMutation({
    mutationFn: () => api("/marketplace/listings", { method: "POST", body: {
      batch_id: form.batch_id, quantity_kg: form.kg, asking_price_paise_per_kg: form.price ? Math.round(Number(form.price) * 100) : null,
      price_is_hypothetical: true, quality_notes: form.notes || null } }),
    onSuccess: () => { toast.success(t("common.saved")); invalidate(qc); onClose(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{t("market.newListing")}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <Field label={t("inventory.batch")} htmlFor="ml-batch" required>
            <Select id="ml-batch" value={form.batch_id} onChange={(e) => setForm({ ...form, batch_id: e.target.value })}>
              <option value="">—</option>
              {batches.data?.items.filter((b) => b.category_code !== "mixed_unsorted" && b.processing_eligible).map((b) => (
                <option key={b.id} value={b.id}>{b.code} · {b.category_label} · {formatKg(b.current_weight_kg, locale)}</option>
              ))}
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("transfers.kg")} htmlFor="ml-kg" required><Input id="ml-kg" inputMode="decimal" value={form.kg} onChange={(e) => setForm({ ...form, kg: e.target.value })} /></Field>
            <Field label={t("market.askingPrice")} htmlFor="ml-price"><Input id="ml-price" inputMode="decimal" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} /></Field>
          </div>
          <Field label={t("market.quality")} htmlFor="ml-notes"><Textarea id="ml-notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
          <p className="text-xs text-muted-foreground">{t("market.hypothetical")}</p>
        </div>
        <DialogFooter><Button disabled={!form.batch_id || !(Number(form.kg) > 0) || save.isPending} onClick={() => save.mutate()}>{t("common.save")}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ListingCard({ x }: { x: Listing }) {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const seller = hasRole(user, "mrf_operator");
  const buyer = hasRole(user, "processor");
  const [offer, setOffer] = useState({ kg: String(x.quantity_kg), price: "" });
  const act = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) => api(`/marketplace/${path}`, { method: "POST", body }),
    onSuccess: () => { toast.success(t("common.saved")); invalidate(qc); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const today = new Date().toISOString().slice(0, 10);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          {x.category_label} · {formatKg(x.quantity_kg, locale)}
          <StatusBadge value={x.status} />
          <OriginBadge origin={x.data_origin} />
        </CardTitle>
        <CardDescription>
          {x.facility_name} · {x.batch_code}
          {x.asking_price_paise_per_kg != null && ` · ${t("market.asking", { price: formatINR(x.asking_price_paise_per_kg, locale) })}`}
          {x.price_is_hypothetical && <Badge tone="warning" className="ml-1">{t("market.sample")}</Badge>}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        {x.verification_status === "suspected" && <p className="text-amber-700 dark:text-amber-400">{t("transfers.suspectedNote")}</p>}
        {x.quality_notes && <p className="text-muted-foreground">{x.quality_notes}</p>}
        {x.offers.length > 0 && (
          <ul className="grid gap-2">
            {x.offers.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-2">
                <span>
                  {o.buyer_name} · {t(`market.kinds.${o.kind}`)} · {formatKg(o.quantity_kg, locale)}
                  {o.price_paise_per_kg != null && ` @ ${formatINR(o.price_paise_per_kg, locale)}/kg`}
                </span>
                <span className="flex items-center gap-1.5">
                  <StatusBadge value={o.status} />
                  {seller && o.status === "offered" && (
                    <>
                      <Button size="sm" onClick={() => act.mutate({ path: `offers/${o.id}/respond`, body: { decision: "accept" } })}>{t("market.accept")}</Button>
                      <Button size="sm" variant="outline" onClick={() => act.mutate({ path: `offers/${o.id}/respond`, body: { decision: "reject" } })}>{t("market.reject")}</Button>
                    </>
                  )}
                  {seller && o.status === "accepted" && !o.sale_id && (
                    <Button size="sm" onClick={() => act.mutate({ path: `offers/${o.id}/sale`, body: { quantity_kg: String(o.quantity_kg), unit_price_paise: o.price_paise_per_kg ?? 0, sold_on: today } })}>
                      {t("market.recordSale")}
                    </Button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
        {buyer && x.status === "open" && (
          <div className="grid grid-cols-[1fr_1fr_auto_auto] items-end gap-2">
            <Field label={t("transfers.kg")} htmlFor={`of-kg-${x.id}`}><Input id={`of-kg-${x.id}`} inputMode="decimal" value={offer.kg} onChange={(e) => setOffer({ ...offer, kg: e.target.value })} /></Field>
            <Field label={t("market.pricePerKg")} htmlFor={`of-p-${x.id}`}><Input id={`of-p-${x.id}`} inputMode="decimal" value={offer.price} onChange={(e) => setOffer({ ...offer, price: e.target.value })} /></Field>
            <Button variant="outline" onClick={() => act.mutate({ path: `listings/${x.id}/offers`, body: { kind: "quote_request", quantity_kg: offer.kg } })}>{t("market.askQuote")}</Button>
            <Button disabled={!offer.price} onClick={() => act.mutate({ path: `listings/${x.id}/offers`, body: { kind: "offer", quantity_kg: offer.kg, price_paise_per_kg: Math.round(Number(offer.price) * 100) } })}>{t("market.offer")}</Button>
          </div>
        )}
        {seller && ["open", "reserved"].includes(x.status) && (
          <Button size="sm" variant="ghost" className="justify-self-start" onClick={() => act.mutate({ path: `listings/${x.id}/withdraw` })}>{t("market.withdraw")}</Button>
        )}
      </CardContent>
    </Card>
  );
}

export default function MarketplacePage() {
  const { t } = useT();
  const user = useAuth((s) => s.user);
  const [status, setStatus] = useState("");
  const list = useApi<Listing[]>("/marketplace/listings", { status: status || undefined });
  const [open, setOpen] = useState(false);
  return (
    <>
      <PageHeader title={t("nav.items.marketplace")} description={t("market.subtitle")}
        actions={hasRole(user, "mrf_operator") && <Button onClick={() => setOpen(true)}><Plus /> {t("market.newListing")}</Button>} />
      <Alert tone="info" className="mb-4">{t("market.notice")}</Alert>
      <Select aria-label={t("common.status")} value={status} onChange={(e) => setStatus(e.target.value)} className="mb-4 w-48">
        <option value="">{t("common.all")}</option>
        {["open", "reserved", "sold", "withdrawn"].map((s) => <option key={s} value={s}>{t(`status.${s}`)}</option>)}
      </Select>
      {!list.data ? <Skeleton className="h-48" /> : list.data.length === 0 ? <EmptyState icon={Store} title={t("market.empty")} /> : (
        <div className="grid gap-4 lg:grid-cols-2">{list.data.map((x) => <ListingCard key={x.id} x={x} />)}</div>
      )}
      {open && <NewListing onClose={() => setOpen(false)} />}
    </>
  );
}
