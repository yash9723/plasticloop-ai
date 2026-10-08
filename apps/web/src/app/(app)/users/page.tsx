"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { type Column, DataTable } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useT } from "@/i18n/i18n";
import { type Page, api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useLabels } from "@/lib/lookups";
import { useApi, usePagedList } from "@/lib/query";
import type { Organization, UserRow } from "@/lib/types";
import { formatDate, relativeTime } from "@/lib/utils";

interface Invitation {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  invite_path: string | null;
}

function InviteDialog() {
  const { t } = useT();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const labels = useLabels();
  const orgs = useApi<Page<Organization>>("/organizations", { page_size: 100 });
  const superAdmin = user?.roles.includes("super_admin");
  const roles = superAdmin ? ["gp_admin", "collector", "driver", "mrf_operator", "processor", "evaluator", "super_admin"] : ["collector", "driver"];
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ email: "", role: roles[0], organization_id: "", village_id: "" });
  const [link, setLink] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => api<Invitation>("/auth/invitations", { method: "POST", body: { ...f, village_id: f.village_id || null } }),
    onSuccess: (inv) => {
      setLink(`${window.location.origin}${inv.invite_path}`);
      qc.invalidateQueries({ queryKey: ["/auth/invitations"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setLink(null); }}>
      <DialogTrigger asChild>
        <Button>
          <UserPlus /> {t("users.invite")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("users.invite")}</DialogTitle>
          <DialogDescription>{t("users.inviteHint")}</DialogDescription>
        </DialogHeader>
        {link ? (
          <div className="grid gap-3">
            <Alert tone="success">
              <AlertDescription>{t("users.inviteCreated")}</AlertDescription>
            </Alert>
            <div className="flex gap-2">
              <Input readOnly value={link} className="font-mono text-xs" />
              <Button variant="outline" onClick={() => navigator.clipboard.writeText(link).then(() => toast.success(t("common.copied")))}>
                <Copy /> {t("common.copy")}
              </Button>
            </div>
          </div>
        ) : (
          <div className="grid gap-4">
            <Field label={t("common.email")} htmlFor="i-email" required>
              <Input id="i-email" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("users.role")} htmlFor="i-role">
                <Select id="i-role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
                  {roles.map((r) => (
                    <option key={r} value={r}>
                      {t(`roles.${r}`)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label={t("users.organization")} htmlFor="i-org" required>
                <Select id="i-org" value={f.organization_id} onChange={(e) => setF({ ...f, organization_id: e.target.value })}>
                  <option value="">—</option>
                  {orgs.data?.items
                    .filter((o) => superAdmin || user?.memberships.some((m) => m.organization_id === o.id))
                    .map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name}
                      </option>
                    ))}
                </Select>
              </Field>
            </div>
            <Field label={t("common.village")} htmlFor="i-village" hint={t("users.villageHint")}>
              <Select id="i-village" value={f.village_id} onChange={(e) => setF({ ...f, village_id: e.target.value })}>
                <option value="">{t("common.all")}</option>
                {labels.villages
                  .filter((v) => !f.organization_id || v.organization_id === f.organization_id)
                  .map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name}
                    </option>
                  ))}
              </Select>
            </Field>
          </div>
        )}
        {!link && (
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button onClick={() => create.mutate()} disabled={!f.email.includes("@") || !f.organization_id || create.isPending}>
              {t("users.createInvite")}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function UsersPage() {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const list = usePagedList<UserRow>("/users", { sort: "name" });
  const invites = useApi<Invitation[]>("/auth/invitations");
  const toggle = useMutation({
    mutationFn: (u: UserRow) => api(`/users/${u.id}/${u.is_active ? "deactivate" : "activate"}`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["/users"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const columns: Column<UserRow>[] = [
    { key: "name", header: t("common.name"), sortKey: "name", cell: (r) => <span className="font-medium">{r.full_name}</span> },
    { key: "email", header: t("common.email"), cell: (r) => <span className="text-muted-foreground">{r.email}</span> },
    { key: "roles", header: t("users.role"), cell: (r) => <span className="flex flex-wrap gap-1">{r.role_keys.map((k) => <Badge key={k} tone="primary">{t(`roles.${k}`)}</Badge>)}</span> },
    { key: "login", header: t("users.lastLogin"), sortKey: "last_login", cell: (r) => (r.last_login_at ? relativeTime(r.last_login_at, locale) : t("common.never")) },
    { key: "status", header: t("common.status"), cell: (r) => <StatusBadge value={r.is_active ? "active" : "inactive"} /> },
    {
      key: "actions",
      header: <span className="sr-only">{t("common.actions")}</span>,
      align: "right",
      cell: (r) =>
        r.id !== user?.id && (
          <Button size="sm" variant="ghost" onClick={() => toggle.mutate(r)} disabled={toggle.isPending}>
            {r.is_active ? t("users.deactivate") : t("users.activate")}
          </Button>
        ),
    },
  ];
  return (
    <>
      <PageHeader title={t("nav.items.users")} description={t("users.subtitle")} actions={hasRole(user, "gp_admin") && <InviteDialog />} />
      <div className="mb-4 max-w-sm">
        <Input placeholder={t("users.search")} aria-label={t("common.search")} onChange={(e) => list.setFilter("q", e.target.value || undefined)} />
      </div>
      <DataTable columns={columns} rows={list.data?.items} rowKey={(r) => r.id} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        sort={list.sort} onSortChange={list.setSort} />
      <Pagination page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPageChange={list.setPage} />
      {!!invites.data?.length && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>{t("users.invitations")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            {invites.data.map((i) => (
              <div key={i.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm">
                <span>
                  {i.email} · {t(`roles.${i.role}`)}
                </span>
                <span className="text-xs text-muted-foreground">
                  {i.accepted_at ? t("users.accepted") : i.revoked_at ? t("users.revoked") : t("users.expires", { date: formatDate(i.expires_at, locale) })}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </>
  );
}
