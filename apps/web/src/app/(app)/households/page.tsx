"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { type Column, DataTable } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useLabels } from "@/lib/lookups";
import { usePagedList } from "@/lib/query";
import type { Household } from "@/lib/types";

function NewHouseholdDialog() {
  const { t } = useT();
  const qc = useQueryClient();
  const labels = useLabels();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ village_id: "", head_name: "", phone: "", address_line: "", members_count: "" });
  const create = useMutation({
    mutationFn: () =>
      api("/households", {
        method: "POST",
        body: { ...f, phone: f.phone || null, address_line: f.address_line || null, members_count: f.members_count ? Number(f.members_count) : null },
      }),
    onSuccess: () => {
      toast.success(t("common.saved"));
      qc.invalidateQueries({ queryKey: ["/households"] });
      setOpen(false);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus /> {t("households.add")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("households.add")}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <Field label={t("common.village")} htmlFor="h-village" required>
            <Select id="h-village" value={f.village_id} onChange={(e) => setF({ ...f, village_id: e.target.value })}>
              <option value="">{t("auth.selectVillage")}</option>
              {labels.villages.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("households.head")} htmlFor="h-name" required>
            <Input id="h-name" value={f.head_name} onChange={(e) => setF({ ...f, head_name: e.target.value })} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("common.phone")} htmlFor="h-phone" hint={t("common.optional")}>
              <Input id="h-phone" type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
            </Field>
            <Field label={t("households.members")} htmlFor="h-members">
              <Input id="h-members" inputMode="numeric" value={f.members_count} onChange={(e) => setF({ ...f, members_count: e.target.value })} />
            </Field>
          </div>
          <Field label={t("common.address")} htmlFor="h-address" hint={t("auth.addressHint")}>
            <Input id="h-address" value={f.address_line} onChange={(e) => setF({ ...f, address_line: e.target.value })} />
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => create.mutate()} disabled={!f.village_id || f.head_name.trim().length < 2 || create.isPending}>
            {t("common.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function HouseholdsPage() {
  const { t } = useT();
  const router = useRouter();
  const user = useAuth((s) => s.user);
  const labels = useLabels();
  const list = usePagedList<Household>("/households", { sort: "code" });
  const columns: Column<Household>[] = [
    { key: "code", header: t("common.code"), sortKey: "code", cell: (r) => <span className="font-medium whitespace-nowrap">{r.household_code}</span> },
    { key: "name", header: t("households.head"), sortKey: "name", cell: (r) => r.head_name },
    { key: "village", header: t("common.village"), cell: (r) => <span className="whitespace-nowrap">{labels.village(r.village_id)}</span> },
    { key: "members", header: t("households.members"), align: "right", cell: (r) => r.members_count ?? "—" },
    { key: "account", header: t("households.account"), cell: (r) => (r.has_account ? t("common.yes") : t("common.no")) },
    {
      key: "status",
      header: t("common.status"),
      cell: (r) => (
        <span className="flex gap-1">
          <StatusBadge value={r.active ? "active" : "inactive"} />
          {r.is_sample && <OriginBadge origin="demo_seed" />}
        </span>
      ),
    },
  ];
  return (
    <>
      <PageHeader title={t("nav.items.households")} description={t("households.subtitle")} actions={hasRole(user, "gp_admin") && <NewHouseholdDialog />} />
      <div className="mb-4 grid gap-2 sm:grid-cols-2">
        <Input placeholder={t("households.search")} aria-label={t("common.search")} onChange={(e) => list.setFilter("q", e.target.value || undefined)} />
        <Select aria-label={t("common.village")} onChange={(e) => list.setFilter("village_id", e.target.value || undefined)}>
          <option value="">{t("collections.allVillages")}</option>
          {labels.villages.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </Select>
      </div>
      <DataTable columns={columns} rows={list.data?.items} rowKey={(r) => r.id} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        sort={list.sort} onSortChange={list.setSort} onRowClick={(r) => router.push(`/households/${r.id}`)} />
      <Pagination page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPageChange={list.setPage} />
    </>
  );
}
