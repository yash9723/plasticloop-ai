"use client";

import { Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { LanguageSwitcher } from "@/components/common/language-switcher";
import { ThemeToggle } from "@/components/common/theme-toggle";
import { BrandLockup } from "@/components/layout/brand";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { useT } from "@/i18n/i18n";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/how-it-works", key: "howItWorks" },
  { href: "/impact", key: "impact" },
  { href: "/about", key: "about" },
  { href: "/contact", key: "contact" },
];

export function PublicHeader() {
  const { t } = useT();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-30 border-b bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:px-6">
        <Link href="/" aria-label="PlasticLoop AI home">
          <BrandLockup />
        </Link>
        <nav className="ml-6 hidden items-center gap-1 md:flex" aria-label={t("nav.menu")}>
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={cn(
                "rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground",
                pathname === l.href && "font-medium text-foreground",
              )}
            >
              {t(`nav.items.${l.key}`)}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <LanguageSwitcher />
          <ThemeToggle />
          <Button asChild className="ml-1 hidden sm:inline-flex">
            <Link href="/login">{t("nav.items.login")}</Link>
          </Button>
          <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setOpen(true)} aria-label={t("nav.openMenu")}>
            <Menu />
          </Button>
        </div>
      </div>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="p-6">
          <SheetTitle>{t("nav.menu")}</SheetTitle>
          <nav className="mt-6 grid gap-1">
            {[...LINKS, { href: "/login", key: "login" }, { href: "/register", key: "register" }].map((l) => (
              <Link key={l.href} href={l.href} onClick={() => setOpen(false)} className="rounded-lg px-3 py-3 text-base hover:bg-muted">
                {t(`nav.items.${l.key}`)}
              </Link>
            ))}
          </nav>
        </SheetContent>
      </Sheet>
    </header>
  );
}

export function PublicFooter() {
  const { t } = useT();
  return (
    <footer className="border-t bg-card">
      <div className="mx-auto grid max-w-6xl gap-6 px-4 py-10 text-sm sm:px-6 md:grid-cols-[2fr_1fr_1fr]">
        <div>
          <BrandLockup />
          <p className="mt-3 max-w-md text-muted-foreground">{t("public.footer.about")}</p>
          <p className="mt-3 text-xs text-muted-foreground">{t("public.footer.honesty")}</p>
        </div>
        <div>
          <p className="font-medium">{t("public.footer.platform")}</p>
          <ul className="mt-2 space-y-1.5 text-muted-foreground">
            {LINKS.map((l) => (
              <li key={l.href}>
                <Link href={l.href} className="hover:text-foreground">
                  {t(`nav.items.${l.key}`)}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="font-medium">{t("public.footer.access")}</p>
          <ul className="mt-2 space-y-1.5 text-muted-foreground">
            <li>
              <Link href="/login" className="hover:text-foreground">
                {t("nav.items.login")}
              </Link>
            </li>
            <li>
              <Link href="/register" className="hover:text-foreground">
                {t("nav.items.register")}
              </Link>
            </li>
          </ul>
        </div>
      </div>
      <div className="border-t py-4 text-center text-xs text-muted-foreground">{t("public.footer.sih")}</div>
    </footer>
  );
}
