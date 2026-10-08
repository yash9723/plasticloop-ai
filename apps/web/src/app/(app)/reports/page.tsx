"use client";

import { Download, FileText } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Field } from "@/components/common/field";
import { PageHeader } from "@/components/common/page-header";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useT } from "@/i18n/i18n";
import { downloadFile, errorMessage } from "@/lib/api";

const KINDS = ["collections", "intakes", "inventory", "transfers", "outcomes", "finance"] as const;
const iso = (d: Date) => d.toISOString().slice(0, 10);

export default function ReportsPage() {
  const { t } = useT();
  const [range, setRange] = useState(() => ({ from: iso(new Date(Date.now() - 30 * 86400_000)), to: iso(new Date()) }));
  const [busy, setBusy] = useState<string | null>(null);
  const query = { date_from: `${range.from}T00:00:00Z`, date_to: `${range.to}T23:59:59Z` };
  const get = async (key: string, path: string, filename: string) => {
    setBusy(key);
    try {
      await downloadFile(path, filename, query);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <PageHeader title={t("nav.items.reports")} description={t("reports.subtitle")} />
      <Card className="mb-4">
        <CardContent className="grid gap-3 pt-5 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <Field label={t("common.from")} htmlFor="rp-from"><Input id="rp-from" type="date" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} /></Field>
          <Field label={t("common.to")} htmlFor="rp-to"><Input id="rp-to" type="date" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} /></Field>
          <Button onClick={() => get("pdf", "/reports/summary.pdf", `plasticloop-summary-${range.from}-${range.to}.pdf`)} disabled={busy !== null}>
            <FileText /> {t("reports.pdf")}
          </Button>
        </CardContent>
      </Card>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {KINDS.map((k) => (
          <Card key={k}>
            <CardHeader>
              <CardTitle className="text-base">{t(`reports.kinds.${k}.title`)}</CardTitle>
              <CardDescription>{t(`reports.kinds.${k}.desc`)}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" disabled={busy !== null} onClick={() => get(k, `/reports/${k}.csv`, `plasticloop-${k}-${range.from}-${range.to}.csv`)}>
                <Download /> {t("common.exportCsv")}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
      <Alert tone="info" className="mt-4">{t("reports.notice")}</Alert>
    </>
  );
}
