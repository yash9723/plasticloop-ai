import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const INTL_LOCALE: Record<string, string> = { en: "en-IN", hi: "hi-IN", te: "te-IN" };
export const intlLocale = (locale: string) => INTL_LOCALE[locale] ?? "en-IN";

export function formatNumber(value: number | null | undefined, locale = "en", digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(intlLocale(locale), { maximumFractionDigits: digits }).format(value);
}

/** Display weight. `exact` keeps all 3 decimals (gram precision) for forms where the user must match a recorded value. */
export function formatKg(value: number | null | undefined, locale = "en", exact = false) {
  if (value === null || value === undefined) return "—";
  if (exact) return `${formatNumber(value, locale, 3)} kg`;
  if (Math.abs(value) >= 1000) return `${formatNumber(value / 1000, locale, 2)} t`;
  return `${formatNumber(value, locale, value < 10 ? 2 : 1)} kg`;
}

/** Money is stored as integer paise. */
/** Metres → "12.3 km". */
export function formatKm(metres: number | null | undefined, locale = "en") {
  if (metres === null || metres === undefined) return "—";
  return `${new Intl.NumberFormat(intlLocale(locale), { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(metres / 1000)} km`;
}

/** Seconds → "1 h 05 min" / "42 min". */
export function formatDuration(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "—";
  const m = Math.round(seconds / 60);
  return m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min` : `${m} min`;
}

export function formatINR(paise: number | null | undefined, locale = "en") {
  if (paise === null || paise === undefined) return "—";
  return new Intl.NumberFormat(intlLocale(locale), { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(paise / 100);
}

export function formatDate(value: string | Date | null | undefined, locale = "en") {
  if (!value) return "—";
  return new Intl.DateTimeFormat(intlLocale(locale), { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

export function formatDateTime(value: string | Date | null | undefined, locale = "en") {
  if (!value) return "—";
  return new Intl.DateTimeFormat(intlLocale(locale), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(
    new Date(value),
  );
}

export function relativeTime(value: string | number | Date | null | undefined, locale = "en") {
  if (!value) return "—";
  const diff = (new Date(value).getTime() - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(intlLocale(locale), { numeric: "auto" });
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["second", 60],
    ["minute", 60],
    ["hour", 24],
    ["day", 30],
    ["month", 12],
    ["year", Infinity],
  ];
  let v = diff;
  for (const [unit, size] of steps) {
    if (Math.abs(v) < size) return rtf.format(Math.round(v), unit);
    v /= size;
  }
  return "—";
}

/** RFC 4122 v4 UUID that also works on plain-HTTP LAN origins (where crypto.randomUUID is unavailable). */
export function uuidv4(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto && window.isSecureContext) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export function toQuery(params: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}
