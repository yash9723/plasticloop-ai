"use client";

import { PlusCircle, QrCode, Waypoints } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { create } from "zustand";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { useT } from "@/i18n/i18n";
import { hasRole, isReadOnly, useAuth } from "@/lib/auth-store";
import { visibleNav } from "@/lib/nav";

export const useCommandMenu = create<{ open: boolean; setOpen: (open: boolean) => void }>()((set) => ({
  open: false,
  setOpen: (open) => set({ open }),
}));

export function CommandMenu() {
  const { t } = useT();
  const router = useRouter();
  const { open, setOpen } = useCommandMenu();
  const user = useAuth((s) => s.user);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!useCommandMenu.getState().open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };
  const canAct = user && !isReadOnly(user);

  return (
    <CommandDialog open={open} onOpenChange={setOpen} title={t("common.search")}>
      <CommandInput placeholder={t("common.searchPlaceholder")} />
      <CommandList>
        <CommandEmpty>{t("common.noResults")}</CommandEmpty>
        {canAct && (
          <CommandGroup heading={t("command.actions")}>
            {hasRole(user, "collector", "gp_admin", "driver") && (
              <>
                <CommandItem onSelect={() => go("/collector?scan=1")}>
                  <QrCode /> {t("command.scanQr")}
                </CommandItem>
                <CommandItem onSelect={() => go("/collections/new")}>
                  <PlusCircle /> {t("command.newCollection")}
                </CommandItem>
              </>
            )}
            {hasRole(user, "gp_admin") && (
              <CommandItem onSelect={() => go("/routes/planner")}>
                <Waypoints /> {t("command.planRoute")}
              </CommandItem>
            )}
          </CommandGroup>
        )}
        {visibleNav(user?.roles ?? []).map((section) => (
          <CommandGroup key={section.key} heading={t(`nav.sections.${section.key}`)}>
            {section.items.map((item) => (
              <CommandItem key={item.href} value={`${t(`nav.items.${item.key}`)} ${item.href}`} onSelect={() => go(item.href)}>
                <item.icon /> {t(`nav.items.${item.key}`)}
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </CommandDialog>
  );
}
