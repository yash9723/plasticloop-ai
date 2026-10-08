"use client";

import { FlaskConical, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useT } from "@/i18n/i18n";
import { isReadOnly, useAuth } from "@/lib/auth-store";

export function DemoBanner() {
  const { t } = useT();
  const user = useAuth((s) => s.user);
  const [hidden, setHidden] = useState(() => {
    try {
      return sessionStorage.getItem("pl_demo_banner") === "hidden";
    } catch {
      return false;
    }
  });
  if (!user?.demo_mode || hidden) return null;
  const dismiss = () => {
    setHidden(true);
    try {
      sessionStorage.setItem("pl_demo_banner", "hidden");
    } catch {
      /* ignore */
    }
  };
  return (
    <div className="flex items-center gap-2 bg-[repeating-linear-gradient(135deg,#fef3c7_0_10px,#fde68a_10px_20px)] px-4 py-1.5 text-xs font-medium text-amber-950 dark:bg-[repeating-linear-gradient(135deg,#422006_0_10px,#713f12_10px_20px)] dark:text-amber-100">
      <FlaskConical className="size-3.5 shrink-0" aria-hidden />
      <p className="flex-1">
        {t("app.demoBanner")} {isReadOnly(user) && <strong className="ml-1">{t("app.readOnly")}</strong>}{" "}
        <Link href="/demo" className="underline underline-offset-2">
          {t("nav.items.demo")}
        </Link>
      </p>
      <button type="button" onClick={dismiss} className="rounded p-0.5 hover:bg-black/10" aria-label={t("common.close")}>
        <X className="size-3.5" />
      </button>
    </div>
  );
}
