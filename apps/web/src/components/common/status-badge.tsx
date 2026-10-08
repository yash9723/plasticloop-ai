"use client";

import { Badge } from "@/components/ui/badge";
import { useT } from "@/i18n/i18n";

type Tone = "neutral" | "primary" | "success" | "warning" | "danger" | "info";

const TONES: Record<string, Tone> = {
  // success
  active: "success", ok: "success", online: "success", completed: "success", synced: "success", accepted: "success",
  resolved: "success", calibrated: "success", verified_with_evidence: "success", reviewed_accepted: "success",
  reviewed_verified: "success", recycled_with_evidence: "success", recovered_documented_process: "success", paid: "success",
  sold: "success", pass: "success", closed: "neutral",
  // in progress / attention
  submitted: "info", assigned: "info", in_progress: "info", planned: "info", allocated: "info", dispatched: "info",
  received: "info", accepted_for_processing: "info", offered: "info", quote_requested: "info", open: "warning",
  queued: "warning", syncing: "info", pending: "warning", stale: "warning", suspected: "warning", under_review: "warning",
  partially_accepted: "warning", awaiting_confirmation: "warning", flagged: "warning", conflict: "warning", due: "warning",
  uncalibrated: "warning", partially_paid: "warning", reserved: "info", unverified: "neutral", submitted_docs: "info",
  // problems
  failed: "danger", rejected: "danger", offline: "danger", verification_rejected: "danger", reviewed_rejected: "danger",
  inactive: "neutral", cancelled: "neutral", depleted: "neutral", never_seen: "neutral", draft: "neutral", skipped: "neutral",
  withdrawn: "neutral", missed: "danger", fail: "danger", none: "neutral", not_submitted: "neutral",
  out_of_range: "danger", negative_drift: "warning", sensor_error: "danger", clock_skew: "warning",
};

const humanize = (v: string) => v.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

/** Status pill. Labels come from `status.<value>` translations, falling back to a humanised value. */
export function StatusBadge({ value, className }: { value: string | null | undefined; className?: string }) {
  const { t } = useT();
  if (!value) return null;
  const key = `status.${value}`;
  const label = t(key);
  return (
    <Badge tone={TONES[value] ?? "neutral"} className={className}>
      {label === key ? humanize(value) : label}
    </Badge>
  );
}
