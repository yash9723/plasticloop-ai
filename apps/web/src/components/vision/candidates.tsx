"use client";

import { Progress } from "@/components/ui/progress";
import { useT } from "@/i18n/i18n";
import type { VisionPrediction } from "@/lib/types";

/** Top suggestions with their scores. Scores are the adapter's own numbers, not calibrated probabilities. */
export function Candidates({ prediction, limit = 4 }: { prediction: VisionPrediction; limit?: number }) {
  const { t } = useT();
  return (
    <ul className="grid gap-2">
      {prediction.candidates.slice(0, limit).map((c) => (
        <li key={String(c.label)}>
          <div className="mb-1 flex justify-between text-sm">
            <span>{t(`vision.labels.${c.label}`)}</span>
            <span className="tabular text-muted-foreground">{Math.round(Number(c.score) * 100)}%</span>
          </div>
          <Progress value={Number(c.score) * 100} className="h-1.5" />
        </li>
      ))}
    </ul>
  );
}
