"use client";

import Link from "next/link";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n/i18n";

export default function NotFound() {
  const { t } = useT();
  return (
    <main className="grid min-h-dvh place-items-center px-4">
      <div className="max-w-md text-center">
        <Compass className="mx-auto mb-4 size-12 text-muted-foreground" aria-hidden />
        <h1 className="text-2xl font-semibold">{t("errors.notFoundTitle")}</h1>
        <p className="mt-2 text-muted-foreground">{t("errors.notFoundBody")}</p>
        <Button asChild className="mt-6">
          <Link href="/dashboard">{t("nav.items.dashboard")}</Link>
        </Button>
      </div>
    </main>
  );
}
