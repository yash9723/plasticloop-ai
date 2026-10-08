"use client";

import { KeyRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Field } from "@/components/common/field";
import { PageHeader } from "@/components/common/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { LOCALES, LOCALE_NAMES, type Locale, useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { forgetCachedProfile, useAuth } from "@/lib/auth-store";
import { cn } from "@/lib/utils";

export default function ProfilePage() {
  const { t, locale, setLocale } = useT();
  const router = useRouter();
  const user = useAuth((s) => s.user);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);

  const chooseLanguage = async (l: Locale) => {
    setLocale(l);
    try {
      await api("/users/me", { method: "PATCH", body: { preferred_language: l } });
      toast.success(t("common.saved"));
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  const changePassword = async () => {
    setBusy(true);
    try {
      await api("/auth/change-password", { method: "POST", body: { current_password: current, new_password: next } });
      toast.success(t("profile.passwordChanged"));
      forgetCachedProfile();
      useAuth.getState().clear();
      router.replace("/login");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (!user) return null;
  return (
    <>
      <PageHeader title={t("nav.items.profile")} description={user.email} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{user.full_name}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm">
            <div className="flex flex-wrap gap-1.5">
              {user.roles.map((r) => (
                <Badge key={r} tone="primary">
                  {t(`roles.${r}`)}
                </Badge>
              ))}
            </div>
            {user.memberships.map((m) => (
              <p key={`${m.organization_id}-${m.role}`} className="text-muted-foreground">
                {t(`roles.${m.role}`)} · {m.organization_name}
              </p>
            ))}
            <p>
              <span className="text-muted-foreground">{t("common.phone")}:</span> {user.phone ?? "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div>
              <CardTitle>{t("common.language")}</CardTitle>
              <CardDescription>{t("profile.languageHint")}</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="grid grid-cols-3 gap-2">
            {LOCALES.map((l) => (
              <button
                key={l}
                type="button"
                lang={l}
                aria-pressed={l === locale}
                onClick={() => chooseLanguage(l)}
                className={cn("min-h-14 rounded-xl border-2 text-base font-medium", l === locale ? "border-primary bg-secondary" : "hover:border-primary/40")}
              >
                {LOCALE_NAMES[l]}
              </button>
            ))}
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle className="flex items-center gap-2">
                <KeyRound className="size-5" /> {t("profile.changePassword")}
              </CardTitle>
              <CardDescription>{t("profile.changePasswordHint")}</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="grid max-w-md gap-4">
            <Field label={t("profile.currentPassword")} htmlFor="cur">
              <Input id="cur" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
            </Field>
            <Field label={t("profile.newPassword")} htmlFor="new" hint={t("auth.passwordRules")}>
              <Input id="new" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
            </Field>
            <Button onClick={changePassword} disabled={busy || !current || next.length < 10} className="justify-self-start">
              {t("profile.changePassword")}
            </Button>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
