"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import en from "./messages/en.json";
import hi from "./messages/hi.json";
import te from "./messages/te.json";

export const LOCALES = ["en", "hi", "te"] as const;
export type Locale = (typeof LOCALES)[number];
export const LOCALE_NAMES: Record<Locale, string> = { en: "English", hi: "हिन्दी", te: "తెలుగు" };

const MESSAGES: Record<Locale, unknown> = { en, hi, te };
type Vars = Record<string, string | number>;

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

function lookup(dict: unknown, key: string): unknown {
  return key.split(".").reduce<unknown>((node, part) => (node && typeof node === "object" ? (node as Record<string, unknown>)[part] : undefined), dict);
}

/** Missing keys fall back to English, then to the key itself (visible, so gaps are noticed). */
export function translate(locale: Locale, key: string, vars?: Vars): string {
  const value = lookup(MESSAGES[locale], key) ?? lookup(en, key);
  if (typeof value !== "string") return key;
  return vars ? value.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`)) : value;
}

interface I18nValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, vars?: Vars) => string;
}

const I18nContext = createContext<I18nValue>({ locale: "en", setLocale: () => {}, t: (k) => k });

export function I18nProvider({ initialLocale, children }: { initialLocale: Locale; children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);
  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    document.cookie = `pl_locale=${next}; path=/; max-age=31536000; samesite=lax`;
    document.documentElement.lang = next;
  }, []);
  const t = useCallback((key: string, vars?: Vars) => translate(locale, key, vars), [locale]);
  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export const useT = () => useContext(I18nContext);

/** Pick a translated label stored in data (e.g. waste stream `labels: {hi, te}`), else the default label. */
export function localized(labels: Record<string, unknown> | null | undefined, fallback: string, locale: Locale): string {
  const v = labels?.[locale];
  return typeof v === "string" && v.trim() ? v : fallback;
}
