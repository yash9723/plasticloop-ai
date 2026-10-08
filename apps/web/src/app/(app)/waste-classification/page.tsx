"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Camera, FlaskConical, ScanLine } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { Candidates } from "@/components/vision/candidates";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { compressImage } from "@/lib/offline/sync";
import { useApi } from "@/lib/query";
import type { VisionPrediction } from "@/lib/types";
import { cn } from "@/lib/utils";

interface VisionStatus {
  adapter: { kind: string; name: string; version: string; is_trained_model: boolean; notice: string };
  evaluation: null | {
    generated_at: string; samples: number; accuracy: number | null; macro_f1: number | null; adapter_name: string;
    per_class: { label: string; precision: number; recall: number; f1: number; support: number }[];
    confusion_columns: string[]; confusion: number[][]; labels: string[];
  };
  evaluation_notice: string | null;
}

export default function ClassificationPage() {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const status = useApi<VisionStatus>("/vision/status");
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<VisionPrediction | null>(null);
  const classify = useMutation({
    mutationFn: async (file: File) => {
      const blob = file.type.startsWith("image/") ? await compressImage(file) : file;
      const form = new FormData();
      form.append("file", blob, "sample.jpg");
      return api<VisionPrediction>("/vision/classify", { method: "POST", form });
    },
    onSuccess: (p) => {
      setResult(p);
      qc.invalidateQueries({ queryKey: ["/vision/predictions"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const onFile = (file: File | undefined) => {
    if (!file) return;
    setResult(null);
    setPreview((old) => {
      if (old) URL.revokeObjectURL(old);
      return URL.createObjectURL(file);
    });
    classify.mutate(file);
  };
  const s = status.data;
  const ev = s?.evaluation;

  return (
    <>
      <PageHeader title={t("nav.items.classification")} description={t("vision.subtitle")}
        actions={<Button variant="outline" asChild><Link href="/waste-classification/review"><FlaskConical /> {t("nav.items.classificationReview")}</Link></Button>} />
      {!s ? (
        <Skeleton className="mb-4 h-16" />
      ) : (
        <Alert tone={s.adapter.is_trained_model ? "info" : "warning"} className="mb-4">
          <span className="font-medium">{t(`vision.kinds.${s.adapter.kind}`)}</span> · {s.adapter.name} {s.adapter.version} — {s.adapter.notice}
        </Alert>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base"><ScanLine className="size-4" /> {t("vision.try")}</CardTitle>
            <CardDescription>{t("vision.tryHint")}</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-6 text-center hover:bg-muted/50">
              {preview ? (
                // eslint-disable-next-line @next/next/no-img-element -- local object URL preview
                <img src={preview} alt={t("vision.previewAlt")} className="max-h-56 rounded-lg object-contain" />
              ) : (
                <Camera className="size-8 text-muted-foreground" />
              )}
              <span className="text-sm font-medium">{t("vision.pick")}</span>
              <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => onFile(e.target.files?.[0])} />
            </label>
            {classify.isPending && <Skeleton className="h-24" />}
            {result && (
              <div className="grid gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm text-muted-foreground">{t("vision.suggestion")}:</span>
                  <span className="font-semibold">{result.top_label ? t(`vision.labels.${result.top_label}`) : t("vision.none")}</span>
                  {result.low_confidence && <Badge tone="warning">{t("vision.lowConfidence")}</Badge>}
                </div>
                {result.candidates.length > 0 && <Candidates prediction={result} />}
                <Alert tone="info">{t("vision.suggestionOnly")}</Alert>
                <Button asChild><Link href="/waste-classification/review">{t("vision.reviewNow")}</Link></Button>
              </div>
            )}
          </CardContent>
        </Card>
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle className="text-base">{t("vision.evaluation")}</CardTitle>
            <CardDescription>{ev ? t("vision.evaluatedOn", { n: ev.samples, date: new Date(ev.generated_at).toLocaleDateString(locale) }) : t("vision.notEvaluated")}</CardDescription>
          </CardHeader>
          <CardContent>
            {!ev ? (
              <p className="text-sm text-muted-foreground">{t("vision.howToEvaluate")}</p>
            ) : (
              <div className="grid gap-3">
                <p className="text-sm">{t("vision.scores", { acc: ev.accuracy === null ? "—" : `${Math.round(ev.accuracy * 1000) / 10}%`, f1: ev.macro_f1 ?? "—", model: ev.adapter_name })}</p>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr><th className="p-1 text-left">{t("vision.trueVsPred")}</th>{ev.confusion_columns.map((c) => <th key={c} className="p-1">{c === "(none)" ? "∅" : t(`vision.short.${c}`)}</th>)}</tr>
                    </thead>
                    <tbody>
                      {ev.labels.map((label, i) => (
                        <tr key={label} className="border-t">
                          <th className="p-1 text-left font-medium">{t(`vision.short.${label}`)}</th>
                          {ev.confusion[i].map((n, j) => <td key={j} className={cn("tabular p-1 text-center", i === j && "bg-secondary font-semibold")}>{n}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
