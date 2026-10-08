"use client";

import { CloudOff, Loader2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n/i18n";
import { NetworkError, refreshSession } from "@/lib/api";
import { loadCachedProfile, useAuth } from "@/lib/auth-store";

/** Routes that keep working without a network session (data comes from IndexedDB). */
const OFFLINE_ROUTES = ["/collector", "/help"];

export function AuthGate({ children }: { children: React.ReactNode }) {
  const status = useAuth((s) => s.status);
  const router = useRouter();
  const pathname = usePathname();
  const { t } = useT();

  useEffect(() => {
    if (status !== "unknown") return;
    let cancelled = false;
    refreshSession()
      .then((ok) => {
        if (!ok && !cancelled) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      })
      .catch((err) => {
        if (cancelled) return;
        const cached = err instanceof NetworkError ? loadCachedProfile() : null;
        if (cached) useAuth.getState().setOffline(cached);
        else router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      });
    return () => {
      cancelled = true;
    };
  }, [status, router, pathname]);

  useEffect(() => {
    if (status === "anonymous") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [status, router, pathname]);

  // Leave offline mode as soon as the network comes back.
  useEffect(() => {
    if (status !== "offline") return;
    const retry = () => refreshSession().catch(() => {});
    window.addEventListener("online", retry);
    return () => window.removeEventListener("online", retry);
  }, [status]);

  if (status === "unknown" || status === "anonymous") {
    return (
      <div className="grid min-h-dvh place-items-center" aria-busy="true">
        <Loader2 className="size-6 animate-spin text-muted-foreground" aria-label={t("common.loading")} />
      </div>
    );
  }

  if (status === "offline" && !OFFLINE_ROUTES.some((r) => pathname === r || pathname.startsWith(`${r}/`))) {
    return (
      <div className="grid min-h-[60dvh] place-items-center px-4">
        <div className="max-w-sm text-center">
          <CloudOff className="mx-auto mb-3 size-10 text-warning" aria-hidden />
          <h1 className="text-lg font-semibold">{t("offline.pageNeedsNetwork")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("offline.pageNeedsNetworkHint")}</p>
          <Button asChild size="lg" className="mt-5">
            <Link href="/collector">{t("nav.items.collector")}</Link>
          </Button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
