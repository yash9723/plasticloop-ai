"use client";

import { Check, Languages } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { LOCALES, LOCALE_NAMES, type Locale, useT } from "@/i18n/i18n";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-store";

export function LanguageSwitcher({ compact = true }: { compact?: boolean }) {
  const { locale, setLocale, t } = useT();
  const status = useAuth((s) => s.status);

  const choose = (next: Locale) => {
    setLocale(next);
    if (status === "authenticated") {
      // Persist to the profile so the preference follows the user across devices (best effort).
      api("/users/me", { method: "PATCH", body: { preferred_language: next } }).catch(() => {});
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size={compact ? "icon" : "default"} aria-label={t("common.language")}>
          <Languages />
          {!compact && <span>{LOCALE_NAMES[locale]}</span>}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuLabel>{t("common.language")}</DropdownMenuLabel>
        {LOCALES.map((l) => (
          <DropdownMenuItem key={l} onSelect={() => choose(l)} lang={l}>
            <span className="flex-1">{LOCALE_NAMES[l]}</span>
            {l === locale && <Check />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
