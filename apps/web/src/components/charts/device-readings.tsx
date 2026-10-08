"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useT } from "@/i18n/i18n";
import type { DeviceReading } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

/** Fill % and weight over time. Only `ok` readings are plotted; flagged ones are listed in the table instead. */
export function DeviceReadingsChart({ readings, height = 240 }: { readings: DeviceReading[]; height?: number }) {
  const { t, locale } = useT();
  const data = readings
    .filter((r) => r.quality === "ok")
    .map((r) => ({ ts: new Date(r.device_timestamp).getTime(), fill: r.fill_percent, weight: r.weight_kg }))
    .sort((a, b) => a.ts - b.ts);
  const time = (v: number) => new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" }).format(v);
  return (
    <div style={{ height }} role="img" aria-label={t("devices.chartAria")}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 4, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="ts" type="number" domain={["dataMin", "dataMax"]} scale="time" tickFormatter={time}
            tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} minTickGap={32} />
          <YAxis yAxisId="fill" domain={[0, 100]} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} width={40} unit="%" />
          <YAxis yAxisId="kg" orientation="right" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} width={44} unit=" kg" />
          <Tooltip
            contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 10, fontSize: 12 }}
            labelFormatter={(v) => formatDateTime(new Date(Number(v)), locale)}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line yAxisId="fill" type="monotone" dataKey="fill" name={t("devices.fill")} stroke="var(--chart-1)" strokeWidth={2} dot={false} connectNulls />
          <Line yAxisId="kg" type="monotone" dataKey="weight" name={t("devices.weight")} stroke="var(--chart-3)" strokeWidth={2} dot={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
