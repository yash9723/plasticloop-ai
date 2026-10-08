"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Loader2, UserPlus } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Field } from "@/components/common/field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { type Me, homeFor, useAuth } from "@/lib/auth-store";
import type { InvitationPublic, VillagePublic } from "@/lib/types";

const password = z
  .string()
  .min(10)
  .regex(/[A-Za-z]/)
  .regex(/\d/);
const phone = z.union([z.literal(""), z.string().regex(/^\+?[0-9]{10,15}$/)]);

const citizenSchema = z.object({
  full_name: z.string().min(2).max(120),
  email: z.email(),
  phone,
  village_id: z.string().uuid(),
  address_line: z.string().max(255).optional(),
  password,
  consent: z.literal(true),
});
const inviteSchema = z.object({ full_name: z.string().min(2).max(120), phone, password });

function finish(router: ReturnType<typeof useRouter>, res: { access_token: string; user: Me }) {
  useAuth.getState().setSession(res.access_token, res.user);
  router.replace(homeFor(res.user));
}

function CitizenForm() {
  const { t } = useT();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const villages = useQuery({ queryKey: ["villages-public"], queryFn: () => api<VillagePublic[]>("/villages/public", { auth: false }) });
  const form = useForm<z.infer<typeof citizenSchema>>({
    resolver: zodResolver(citizenSchema),
    defaultValues: { full_name: "", email: "", phone: "", village_id: "", address_line: "", password: "" },
  });
  const e = form.formState.errors;
  const submit = form.handleSubmit(async (v) => {
    setError(null);
    try {
      finish(router, await api("/auth/register", { method: "POST", auth: false, body: { ...v, phone: v.phone || null } }));
    } catch (err) {
      setError(errorMessage(err));
    }
  });
  return (
    <form onSubmit={submit} className="grid gap-4" noValidate>
      {error && (
        <Alert tone="danger">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Field label={t("auth.fullName")} htmlFor="full_name" required error={e.full_name && t("validation.name")}>
        <Input id="full_name" autoComplete="name" {...form.register("full_name")} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("common.email")} htmlFor="email" required error={e.email && t("validation.email")}>
          <Input id="email" type="email" autoComplete="email" {...form.register("email")} />
        </Field>
        <Field label={t("common.phone")} htmlFor="phone" hint={t("common.optional")} error={e.phone && t("validation.phone")}>
          <Input id="phone" type="tel" inputMode="tel" autoComplete="tel" {...form.register("phone")} />
        </Field>
      </div>
      <Field label={t("common.village")} htmlFor="village_id" required error={e.village_id && t("validation.required")}>
        <Select id="village_id" {...form.register("village_id")}>
          <option value="">{t("auth.selectVillage")}</option>
          {villages.data?.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
              {v.district ? `, ${v.district}` : ""}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={t("common.address")} htmlFor="address_line" hint={t("auth.addressHint")}>
        <Input id="address_line" autoComplete="street-address" {...form.register("address_line")} />
      </Field>
      <Field label={t("auth.password")} htmlFor="password" required error={e.password && t("auth.passwordRules")} hint={t("auth.passwordRules")}>
        <Input id="password" type="password" autoComplete="new-password" {...form.register("password")} />
      </Field>
      <label className="flex items-start gap-3 rounded-lg border p-3 text-sm">
        <input type="checkbox" className="mt-0.5 size-4 accent-[var(--primary)]" {...form.register("consent")} />
        <span>
          {t("auth.consent")}
          {e.consent && <span className="mt-1 block text-xs text-danger-foreground">{t("validation.consent")}</span>}
        </span>
      </label>
      <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? <Loader2 className="animate-spin" /> : <UserPlus />}
        {t("auth.createAccount")}
      </Button>
    </form>
  );
}

function InviteForm({ token }: { token: string }) {
  const { t } = useT();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const invite = useQuery({
    queryKey: ["invite", token],
    queryFn: () => api<InvitationPublic>(`/auth/invitations/lookup/${encodeURIComponent(token)}`, { auth: false }),
    retry: false,
  });
  const form = useForm<z.infer<typeof inviteSchema>>({ resolver: zodResolver(inviteSchema), defaultValues: { full_name: "", phone: "", password: "" } });
  const submit = form.handleSubmit(async (v) => {
    setError(null);
    try {
      finish(router, await api("/auth/invitations/accept", { method: "POST", auth: false, body: { ...v, token, phone: v.phone || null } }));
    } catch (err) {
      setError(errorMessage(err));
    }
  });
  if (invite.isError)
    return (
      <Alert tone="danger">
        <AlertDescription>{t("auth.inviteInvalid")}</AlertDescription>
      </Alert>
    );
  return (
    <form onSubmit={submit} className="grid gap-4" noValidate>
      {invite.data && (
        <Alert tone="info">
          <AlertDescription>
            {t("auth.inviteFor", { email: invite.data.email, role: t(`roles.${invite.data.role}`), org: invite.data.organization_name })}
          </AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert tone="danger">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Field label={t("auth.fullName")} htmlFor="full_name" required error={form.formState.errors.full_name && t("validation.name")}>
        <Input id="full_name" autoComplete="name" {...form.register("full_name")} />
      </Field>
      <Field label={t("common.phone")} htmlFor="phone" hint={t("common.optional")} error={form.formState.errors.phone && t("validation.phone")}>
        <Input id="phone" type="tel" inputMode="tel" {...form.register("phone")} />
      </Field>
      <Field label={t("auth.password")} htmlFor="password" required hint={t("auth.passwordRules")} error={form.formState.errors.password && t("auth.passwordRules")}>
        <Input id="password" type="password" autoComplete="new-password" {...form.register("password")} />
      </Field>
      <Button type="submit" size="lg" disabled={form.formState.isSubmitting || !invite.data}>
        {form.formState.isSubmitting ? <Loader2 className="animate-spin" /> : <UserPlus />}
        {t("auth.acceptInvite")}
      </Button>
    </form>
  );
}

function RegisterInner() {
  const { t } = useT();
  const token = useSearchParams().get("invite");
  return (
    <div className="mx-auto max-w-xl px-4 py-12 sm:px-6 lg:py-16">
      <Card>
        <CardHeader className="flex-col items-start">
          <CardTitle className="text-xl">{token ? t("auth.inviteTitle") : t("auth.registerTitle")}</CardTitle>
          <CardDescription>{token ? t("auth.inviteSubtitle") : t("auth.registerSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          {token ? <InviteForm token={token} /> : <CitizenForm />}
          <p className="mt-4 text-center text-sm text-muted-foreground">
            {t("auth.haveAccount")}{" "}
            <Link href="/login" className="font-medium text-primary hover:underline">
              {t("auth.signIn")}
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense>
      <RegisterInner />
    </Suspense>
  );
}
