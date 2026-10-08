"use client";

import { useQueryClient } from "@tanstack/react-query";
import { HelpCircle, LogOut, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useT } from "@/i18n/i18n";
import { api } from "@/lib/api";
import { forgetCachedProfile, useAuth } from "@/lib/auth-store";
import { countPending } from "@/lib/offline/db";

export function UserMenu() {
  const { t } = useT();
  const user = useAuth((s) => s.user);
  const router = useRouter();
  const qc = useQueryClient();
  const initials = (user?.full_name ?? "?")
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const signOut = async () => {
    const pending = user ? await countPending(user.id).catch(() => 0) : 0;
    try {
      await api("/auth/logout", { method: "POST", headers: { "X-Requested-With": "plasticloop" }, auth: false });
    } catch {
      /* offline: the cookie is still revoked on next server contact attempt */
    }
    if (pending > 0) toast.warning(t("offline.pendingOnLogout", { count: pending }));
    else forgetCachedProfile();
    qc.clear();
    useAuth.getState().clear();
    router.replace("/login");
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t("common.account")}>
          <span className="grid size-8 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
            {initials}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-60">
        <DropdownMenuLabel className="text-foreground">
          <span className="block truncate text-sm font-semibold">{user?.full_name}</span>
          <span className="block truncate text-xs font-normal text-muted-foreground">{user?.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/profile">
            <UserRound /> {t("nav.items.profile")}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/help">
            <HelpCircle /> {t("nav.items.help")}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={signOut} className="text-danger-foreground">
          <LogOut className="!text-danger-foreground" /> {t("nav.logout")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
