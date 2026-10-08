"use client";

import { CloudOff } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n/i18n";

/** Served by the service worker when a page that was never cached is opened without a network. */
export default function OfflinePage() {
  const { t } = useT();
  return (
    <main className="grid min-h-dvh place-items-center px-4">
      <div className="max-w-sm text-center">
        <CloudOff className="mx-auto mb-4 size-12 text-warning" aria-hidden />
        <h1 className="text-xl font-semibold">{t("offline.fallbackTitle")}</h1>
        <p className="mt-2 text-muted-foreground">{t("offline.fallbackBody")}</p>
        <Button asChild size="xl" className="mt-6 w-full">
          <Link href="/collector">{t("nav.items.collector")}</Link>
        </Button>
      </div>
    </main>
  );
}
