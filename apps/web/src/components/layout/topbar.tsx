"use client";

import { ChevronRight, Menu, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LanguageSwitcher } from "@/components/common/language-switcher";
import { OfflineIndicator } from "@/components/common/offline-indicator";
import { ThemeToggle } from "@/components/common/theme-toggle";
import { useCommandMenu } from "@/components/layout/command-menu";
import { NotificationBell } from "@/components/layout/notification-bell";
import { UserMenu } from "@/components/layout/user-menu";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n/i18n";
import { NAV, findNavItem } from "@/lib/nav";
import { usePendingCount } from "@/lib/offline/hooks";

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const { t } = useT();
  const pathname = usePathname();
  const item = findNavItem(pathname);
  const section = item ? NAV.find((s) => s.items.includes(item)) : undefined;
  const openSearch = useCommandMenu((s) => s.setOpen);
  const pending = usePendingCount();

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b bg-background/85 px-3 backdrop-blur supports-[backdrop-filter]:bg-background/70 sm:px-5">
      <Button variant="ghost" size="icon" className="lg:hidden" onClick={onMenu} aria-label={t("nav.openMenu")}>
        <Menu />
      </Button>
      <nav aria-label={t("nav.breadcrumb")} className="hidden min-w-0 items-center gap-1 text-sm text-muted-foreground sm:flex">
        {section && <span className="truncate">{t(`nav.sections.${section.key}`)}</span>}
        {item && (
          <>
            <ChevronRight className="size-3.5 shrink-0" aria-hidden />
            <Link href={item.href} className="truncate font-medium text-foreground hover:underline">
              {t(`nav.items.${item.key}`)}
            </Link>
          </>
        )}
      </nav>
      <div className="ml-auto flex items-center gap-1">
        <OfflineIndicator pending={pending} className="mr-1" />
        <Button
          variant="outline"
          size="sm"
          className="hidden h-9 w-56 justify-start gap-2 text-muted-foreground md:inline-flex"
          onClick={() => openSearch(true)}
        >
          <Search />
          <span className="flex-1 text-left">{t("common.searchPlaceholder")}</span>
          <kbd className="rounded border bg-muted px-1.5 text-[10px] font-medium text-foreground">Ctrl K</kbd>
        </Button>
        <Button variant="ghost" size="icon" className="md:hidden" onClick={() => openSearch(true)} aria-label={t("common.search")}>
          <Search />
        </Button>
        <LanguageSwitcher />
        <ThemeToggle />
        <NotificationBell />
        <UserMenu />
      </div>
    </header>
  );
}
