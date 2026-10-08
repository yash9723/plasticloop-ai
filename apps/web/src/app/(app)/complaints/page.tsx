"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Camera, MessageSquarePlus } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { type Column, DataTable } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, isReadOnly, useAuth } from "@/lib/auth-store";
import { useAssignable, useLabels } from "@/lib/lookups";
import { compressImage } from "@/lib/offline/sync";
import { usePagedList } from "@/lib/query";
import type { Complaint } from "@/lib/types";
import { formatDate } from "@/lib/utils";

const CATEGORIES = ["missed_pickup", "overflowing_bin", "damaged_bin", "staff_behaviour", "illegal_dumping", "other"];

function NewComplaintDialog({ defaultOpen }: { defaultOpen: boolean }) {
  const { t } = useT();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const labels = useLabels();
  const [open, setOpen] = useState(defaultOpen);
  const [category, setCategory] = useState("missed_pickup");
  const [description, setDescription] = useState("");
  const [villageId, setVillageId] = useState("");
  const [photo, setPhoto] = useState<Blob | null>(null);
  const staff = hasRole(user, "gp_admin", "collector");
  const create = useMutation({
    mutationFn: async () => {
      let media_id: string | null = null;
      if (photo) {
        const form = new FormData();
        form.append("file", photo, "complaint.jpg");
        form.append("purpose", "complaint_photo");
        media_id = (await api<{ id: string }>("/media", { method: "POST", form })).id;
      }
      return api("/complaints", { method: "POST", body: { category, description, media_id, village_id: staff ? villageId || null : null } });
    },
    onSuccess: () => {
      toast.success(t("complaints.created"));
      qc.invalidateQueries({ queryKey: ["/complaints"] });
      setOpen(false);
      setDescription("");
      setPhoto(null);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <MessageSquarePlus /> {t("complaints.report")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("complaints.report")}</DialogTitle>
          <DialogDescription>{t("complaints.reportHint")}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <Field label={t("complaints.category")} htmlFor="c-cat">
            <Select id="c-cat" value={category} onChange={(e) => setCategory(e.target.value)}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {t(`complaints.categories.${c}`)}
                </option>
              ))}
            </Select>
          </Field>
          {staff && (
            <Field label={t("common.village")} htmlFor="c-village" required>
              <Select id="c-village" value={villageId} onChange={(e) => setVillageId(e.target.value)}>
                <option value="">{t("auth.selectVillage")}</option>
                {labels.villages.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Field label={t("complaints.description")} htmlFor="c-desc" required>
            <Textarea id="c-desc" value={description} maxLength={1000} onChange={(e) => setDescription(e.target.value)} rows={4} />
          </Field>
          <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-dashed px-3 py-3 text-sm">
            <Camera className="size-4" /> {photo ? t("collector.form.retakePhoto") : t("collector.form.addPhoto")}
            <input type="file" accept="image/*" capture="environment" className="sr-only"
              onChange={async (e) => e.target.files?.[0] && setPhoto(await compressImage(e.target.files[0]))} />
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => create.mutate()} disabled={description.trim().length < 5 || (staff && !villageId) || create.isPending}>
            {t("common.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ComplaintActions({ c }: { c: Complaint }) {
  const { t } = useT();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const assignees = useAssignable(hasRole(user, "gp_admin") ? c.village_id : null);
  const update = useMutation({
    mutationFn: (body: Record<string, unknown>) => api(`/complaints/${c.id}`, { method: "PATCH", body: { ...body, version: c.version } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["/complaints"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!hasRole(user, "gp_admin") || c.status === "closed") return null;
  return (
    <div className="flex flex-wrap justify-end gap-1.5">
      {["open", "under_review", "assigned"].includes(c.status) && (
        <Select aria-label={t("complaints.assign")} className="h-8 min-w-32 text-xs" value="" onChange={(e) => e.target.value && update.mutate({ status: "assigned", assigned_to: e.target.value })}>
          <option value="">{t("complaints.assign")}</option>
          {assignees.data?.map((u) => (
            <option key={u.id} value={u.id}>
              {u.full_name}
            </option>
          ))}
        </Select>
      )}
      {c.status !== "resolved" && (
        <Button size="sm" onClick={() => {
          const note = window.prompt(t("complaints.resolutionPrompt"));
          if (note && note.trim().length >= 3) update.mutate({ status: "resolved", resolution_note: note.trim() });
        }}>
          {t("complaints.resolve")}
        </Button>
      )}
      {c.status === "resolved" && (
        <Button size="sm" variant="outline" onClick={() => update.mutate({ status: "closed" })}>
          {t("complaints.close")}
        </Button>
      )}
    </div>
  );
}

function ComplaintsInner() {
  const { t, locale } = useT();
  const params = useSearchParams();
  const user = useAuth((s) => s.user);
  const labels = useLabels();
  const list = usePagedList<Complaint>("/complaints", { sort: "-created" });
  const columns: Column<Complaint>[] = [
    { key: "created", header: t("common.created"), sortKey: "created", cell: (r) => <span className="whitespace-nowrap">{formatDate(r.created_at, locale)}</span> },
    { key: "category", header: t("complaints.category"), cell: (r) => <span className="whitespace-nowrap">{t(`complaints.categories.${r.category}`)}</span> },
    { key: "village", header: t("common.village"), cell: (r) => <span className="whitespace-nowrap">{labels.village(r.village_id)}</span> },
    {
      key: "description",
      header: t("complaints.description"),
      cell: (r) => (
        <span className="block min-w-56 max-w-md">
          <span className="line-clamp-2">{r.description}</span>
          {r.resolution_note && <span className="mt-1 block text-xs text-muted-foreground">↳ {r.resolution_note}</span>}
          {r.photo_url && (
            <a href={r.photo_url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">
              {t("collections.photo")}
            </a>
          )}
        </span>
      ),
    },
    {
      key: "status",
      header: t("common.status"),
      sortKey: "status",
      cell: (r) => (
        <span className="flex gap-1">
          <StatusBadge value={r.status} />
          <OriginBadge origin={r.data_origin} />
        </span>
      ),
    },
    { key: "actions", header: <span className="sr-only">{t("common.actions")}</span>, align: "right", cell: (r) => <ComplaintActions c={r} /> },
  ];
  return (
    <>
      <PageHeader
        title={t("nav.items.complaints")}
        description={t("complaints.subtitle")}
        actions={!isReadOnly(user) && <NewComplaintDialog defaultOpen={params.get("new") === "1"} />}
      />
      <div className="mb-4 max-w-xs">
        <Select aria-label={t("common.status")} onChange={(e) => list.setFilter("status", e.target.value || undefined)}>
          <option value="">{t("common.all")}</option>
          {["open", "assigned", "under_review", "resolved", "closed"].map((s) => (
            <option key={s} value={s}>
              {t(`status.${s}`)}
            </option>
          ))}
        </Select>
      </div>
      <DataTable columns={columns} rows={list.data?.items} rowKey={(r) => r.id} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        sort={list.sort} onSortChange={list.setSort} emptyTitle={t("complaints.empty")} />
      <Pagination page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPageChange={list.setPage} />
    </>
  );
}

export default function ComplaintsPage() {
  return (
    <Suspense>
      <ComplaintsInner />
    </Suspense>
  );
}
