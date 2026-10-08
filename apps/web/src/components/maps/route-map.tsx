"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect, useMemo } from "react";
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";

export type PointTone = "default" | "selected" | "emergency" | "done" | "skipped" | "dropped";

export interface MapPoint {
  id: string;
  lat: number;
  lng: number;
  label: string;
  tone?: PointTone;
  sequence?: number;
  color?: string;
  onClick?: () => void;
}

export interface MapLine {
  id: string;
  color: string;
  positions: [number, number][];
}

export interface MapAnchor {
  id: string;
  lat: number;
  lng: number;
  label: string;
  kind: "depot" | "facility";
}

const TONE: Record<PointTone, { stroke: string; fill: string }> = {
  default: { stroke: "#64748b", fill: "#94a3b8" },
  selected: { stroke: "#166534", fill: "#22c55e" },
  emergency: { stroke: "#b91c1c", fill: "#ef4444" },
  done: { stroke: "#166534", fill: "#86efac" },
  skipped: { stroke: "#b45309", fill: "#fcd34d" },
  dropped: { stroke: "#b91c1c", fill: "#fecaca" },
};

/** Distinct, colour-blind-friendly route colours (Okabe–Ito). */
export const ROUTE_COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"];

function FitBounds({ coords }: { coords: [number, number][] }) {
  const map = useMap();
  const key = coords.map((c) => c.join(",")).join(";");
  useEffect(() => {
    if (coords.length === 1) map.setView(coords[0], 15);
    else if (coords.length > 1) map.fitBounds(L.latLngBounds(coords), { padding: [28, 28], maxZoom: 16 });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refit only when the set of coordinates changes
  }, [key, map]);
  return null;
}

const seqIcon = (n: number, color: string) =>
  L.divIcon({
    className: "",
    html: `<span style="display:grid;place-items:center;width:24px;height:24px;border-radius:9999px;background:${color};color:#fff;font:600 12px/1 system-ui;border:2px solid #fff;box-shadow:0 1px 3px rgb(0 0 0/.35)">${n}</span>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });

const anchorIcon = (kind: MapAnchor["kind"]) =>
  L.divIcon({
    className: "",
    html: `<span style="display:grid;place-items:center;width:28px;height:28px;border-radius:6px;background:${kind === "facility" ? "#0f172a" : "#166534"};color:#fff;font:700 13px/1 system-ui;border:2px solid #fff;box-shadow:0 1px 3px rgb(0 0 0/.35)">${kind === "facility" ? "F" : "D"}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });

/**
 * Client-only Leaflet map (import with next/dynamic, ssr: false). Tiles come from OpenStreetMap and need internet;
 * markers and routes still render without tiles.
 */
export function RouteMap({
  points = [],
  lines = [],
  anchors = [],
  height = 420,
  ariaLabel,
}: {
  points?: MapPoint[];
  lines?: MapLine[];
  anchors?: MapAnchor[];
  height?: number | string;
  ariaLabel: string;
}) {
  const coords = useMemo<[number, number][]>(
    () => [...points.map((p) => [p.lat, p.lng] as [number, number]), ...anchors.map((a) => [a.lat, a.lng] as [number, number])],
    [points, anchors],
  );
  const center: [number, number] = coords[0] ?? [17.95, 78.88];
  return (
    <div style={{ height }} className="overflow-hidden rounded-lg border" role="region" aria-label={ariaLabel}>
      <MapContainer center={center} zoom={13} scrollWheelZoom={false} style={{ height: "100%", width: "100%" }}>
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <FitBounds coords={coords} />
        {lines.map((l) => (
          <Polyline key={l.id} positions={l.positions} pathOptions={{ color: l.color, weight: 4, opacity: 0.85 }} />
        ))}
        {anchors.map((a) => (
          <Marker key={a.id} position={[a.lat, a.lng]} icon={anchorIcon(a.kind)}>
            <Tooltip>{a.label}</Tooltip>
          </Marker>
        ))}
        {points.map((p) =>
          p.sequence !== undefined ? (
            <Marker key={p.id} position={[p.lat, p.lng]} icon={seqIcon(p.sequence, p.color ?? TONE[p.tone ?? "selected"].stroke)}
              eventHandlers={p.onClick ? { click: p.onClick } : undefined}>
              <Tooltip>{p.label}</Tooltip>
            </Marker>
          ) : (
            <CircleMarker key={p.id} center={[p.lat, p.lng]} radius={7}
              pathOptions={{ color: TONE[p.tone ?? "default"].stroke, fillColor: TONE[p.tone ?? "default"].fill, fillOpacity: 0.9, weight: 2 }}
              eventHandlers={p.onClick ? { click: p.onClick } : undefined}>
              <Tooltip>{p.label}</Tooltip>
            </CircleMarker>
          ),
        )}
      </MapContainer>
    </div>
  );
}
