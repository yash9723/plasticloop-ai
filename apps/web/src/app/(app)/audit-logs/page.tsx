"use client";

import { useState } from "react";
import { type Column, DataTable } from "@/components/common/data-table";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useT } from "@/i18n/i18n";
import { usePagedList } from "@/lib/query";
import type { AuditEntry } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export default function AuditLogsPage() {
  const { t, locale } = useT();
  const list = usePagedList<AuditEntry>("/audit-logs", { sort: "-time", pageSize: 50 });
  const [open, setOpen] = useState<AuditEntry | null>(null);
  const columns: Column<AuditEntry>[] = [
    { key: "time", header: t("common.date"), sortKey: "time", cell: (r) => <span className="whitespace-nowrap">{formatDateTime(r.occurred_at, locale)}</span> },
    { key: "actor", header: t("audit.actor"), cell: (r) => <span className="block max-w-56 truncate">{r.actor_label ?? t("audit.system")}</span> },
    { key: "action", header: t("audit.action"), sortKey: "action", cell: (r) => <code className="text-xs">{r.action}</code> },
    { key: "entity", header: t("audit.entity"), cell: (r) => <span className="text-xs">{r.entity_type}{r.entity_id ? ` · ${r.entity_id.slice(0, 8)}` : ""}</span> },
    { key: "detail", header: "", cell: (r) => (r.after || r.before) && <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setOpen(r); }}>{t("common.details")}</Button> },
  ];
  return (
    <>
      <PageHeader title={t("nav.items.auditLogs")} description={t("audit.subtitle")} />
      <Alert tone="info" className="mb-4">{t("audit.notice")}</Alert>
      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        <Input placeholder={t("audit.filterAction")} aria-label={t("audit.action")} onChange={(e) => list.setFilter("action", e.target.value || undefined)} />
        <Input placeholder={t("audit.filterEntity")} aria-label={t("audit.entity")} onChange={(e) => list.setFilter("entity_type", e.target.value || undefined)} />
      </div>
      <DataTable columns={columns} rows={list.data?.items} rowKey={(r) => r.id} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        sort={list.sort} onSortChange={list.setSort} emptyTitle={t("audit.empty")} />
      <Pagination page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPageChange={list.setPage} />
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader><DialogTitle><code>{open?.action}</code></DialogTitle></DialogHeader>
          <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs">{JSON.stringify({ before: open?.before, after: open?.after, request_id: open?.request_id }, null, 2)}</pre>
        </DialogContent>
      </Dialog>
    </>
  );
}
