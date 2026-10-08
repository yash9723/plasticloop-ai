"use client";

import { FlaskConical, Gauge, Hand, Sparkles, Scale } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useT } from "@/i18n/i18n";

/** Makes provenance impossible to miss: simulated and demo records are always labelled. */
export function OriginBadge({ origin, showLive = false }: { origin: string | null | undefined; showLive?: boolean }) {
  const { t } = useT();
  if (origin === "simulated")
    return (
      <Badge tone="simulated" title={t("provenance.simulatedHint")}>
        <FlaskConical aria-hidden /> {t("provenance.simulated")}
      </Badge>
    );
  if (origin === "demo_seed")
    return (
      <Badge tone="info" title={t("provenance.demoHint")}>
        <Sparkles aria-hidden /> {t("provenance.demo")}
      </Badge>
    );
  if (origin === "live" && showLive) return <Badge tone="success">{t("provenance.live")}</Badge>;
  return null;
}

export function MeasurementBadge({ source }: { source: string }) {
  const { t } = useT();
  const map: Record<string, { tone: "success" | "neutral" | "simulated" | "warning"; Icon: typeof Scale }> = {
    device_measured: { tone: "success", Icon: Scale },
    manual_entry: { tone: "neutral", Icon: Hand },
    simulated_sensor: { tone: "simulated", Icon: FlaskConical },
    estimated: { tone: "warning", Icon: Gauge },
  };
  const m = map[source] ?? map.manual_entry;
  return (
    <Badge tone={m.tone}>
      <m.Icon aria-hidden /> {t(`measurement.${source}`)}
    </Badge>
  );
}
