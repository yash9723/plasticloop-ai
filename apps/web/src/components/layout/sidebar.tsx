"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandMark } from "@/components/layout/brand";
import { useT } from "@/i18n/i18n";
import { useAuth } from "@/lib/auth-store";
import { NAV, findNavItem, visibleNav } from "@/lib/nav";
import { cn } from "@/lib/utils";

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useT();
  const pathname = usePathname();
  const user = useAuth((s) => s.user);
  const status = useAuth((s) => s.status);
  const sections = visibleNav(user?.roles ?? []);
  const active = findNavItem(pathname)?.href;
  const org = user?.memberships[0]?.organization_name;

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <Link href="/dashboard" onClick={onNavigate} className="flex items-center gap-2.5 px-5 py-5">
        <BrandMark className="size-8" />
        <span className="leading-tight">
          <span className="block text-[0.95rem] font-semibold text-white">PlasticLoop AI</span>
          <span className="block text-[11px] text-sidebar-muted">SIH26259 · MLP traceability</span>
        </span>
      </Link>
      <nav aria-label={t("nav.menu")} className="flex-1 overflow-y-auto px-3 pb-4">
        {sections.map((section) => (
          <div key={section.key} className="mb-4">
            <p className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-sidebar-muted">
              {t(`nav.sections.${section.key}`)}
            </p>
            <ul className="space-y-0.5">
              {section.items.map((item) => {
                const isActive = item.href === active;
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      aria-current={isActive ? "page" : undefined}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400",
                        isActive
                          ? "bg-sidebar-active font-medium text-sidebar-active-foreground"
                          : "hover:bg-sidebar-hover hover:text-white",
                      )}
                    >
                      <Icon className="size-[18px] shrink-0" aria-hidden />
                      <span className="truncate">{t(`nav.items.${item.key}`)}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
      <div className="border-t border-sidebar-border px-5 py-4 text-xs">
        <p className="truncate font-medium text-white">{user?.full_name}</p>
        <p className="truncate text-sidebar-muted">
          {user?.roles.map((r) => t(`roles.${r}`)).join(" · ")}
          {org ? ` — ${org}` : ""}
        </p>
        {status === "offline" && <p className="mt-1 text-amber-300">{t("offline.badge")}</p>}
      </div>
    </div>
  );
}

export { NAV };
