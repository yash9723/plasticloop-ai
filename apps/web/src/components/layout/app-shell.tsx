"use client";

import { useState } from "react";
import { CommandMenu } from "@/components/layout/command-menu";
import { DemoBanner } from "@/components/layout/demo-banner";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { useT } from "@/i18n/i18n";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { t } = useT();
  return (
    <div className="min-h-dvh bg-background">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        {t("app.skipToContent")}
      </a>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">
        <Sidebar />
      </aside>
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="border-0 bg-sidebar p-0 text-sidebar-foreground">
          <SheetTitle className="sr-only">{t("nav.menu")}</SheetTitle>
          <Sidebar onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>
      <div className="flex min-h-dvh flex-col lg:pl-64">
        <DemoBanner />
        <Topbar onMenu={() => setMobileOpen(true)} />
        <main id="main" className="page-container flex-1">
          {children}
        </main>
      </div>
      <CommandMenu />
    </div>
  );
}
