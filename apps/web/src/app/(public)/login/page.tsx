"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { FlaskConical, Loader2, LogIn } from "lucide-react";
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
import { isLocale, useT } from "@/i18n/i18n";
import { ApiError, api, errorMessage } from "@/lib/api";
import { type Me, homeFor, useAuth } from "@/lib/auth-store";

const schema = z.object({ identifier: z.string().min(3), password: z.string().min(1) });
type FormValues = z.infer<typeof schema>;

interface DemoAccounts {
  password: string;
  accounts: { email: string; role: string; label: string }[];
}

function LoginForm() {
  const { t, setLocale } = useT();
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { identifier: "", password: "" } });
  const demo = useQuery({
    queryKey: ["demo-accounts"],
    queryFn: () => api<DemoAccounts>("/demo/accounts", { auth: false }),
    retry: false,
  });

  const submit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      const res = await api<{ access_token: string; user: Me }>("/auth/login", { method: "POST", body: values, auth: false });
      useAuth.getState().setSession(res.access_token, res.user);
      if (isLocale(res.user.preferred_language)) setLocale(res.user.preferred_language);
      const next = params.get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : homeFor(res.user));
    } catch (err) {
      setError(err instanceof ApiError && err.code === "INVALID_CREDENTIALS" ? t("auth.invalidCredentials") : errorMessage(err));
    }
  });

  return (
    <div className="mx-auto grid max-w-5xl gap-8 px-4 py-12 sm:px-6 lg:grid-cols-[1fr_1.1fr] lg:py-20">
      <Card className="self-start">
        <CardHeader className="flex-col items-start">
          <CardTitle className="text-xl">{t("auth.loginTitle")}</CardTitle>
          <CardDescription>{t("auth.loginSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid gap-4" noValidate>
            {error && (
              <Alert tone="danger">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Field label={t("auth.identifier")} htmlFor="identifier" error={form.formState.errors.identifier && t("validation.required")}>
              <Input id="identifier" autoComplete="username" inputMode="email" {...form.register("identifier")} />
            </Field>
            <Field label={t("auth.password")} htmlFor="password" error={form.formState.errors.password && t("validation.required")}>
              <Input id="password" type="password" autoComplete="current-password" {...form.register("password")} />
            </Field>
            <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? <Loader2 className="animate-spin" /> : <LogIn />}
              {t("auth.signIn")}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              {t("auth.noAccount")}{" "}
              <Link href="/register" className="font-medium text-primary hover:underline">
                {t("auth.registerLink")}
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>

      {demo.data && (
        <Card className="self-start border-amber-300/60 dark:border-amber-900">
          <CardHeader className="flex-col items-start">
            <CardTitle className="flex items-center gap-2">
              <FlaskConical className="size-5 text-warning" aria-hidden /> {t("auth.demoAccounts")}
            </CardTitle>
            <CardDescription>
              {t("auth.demoAccountsHint")} <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground">{demo.data.password}</code>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {demo.data.accounts.map((a) => (
                <li key={a.email}>
                  <button
                    type="button"
                    onClick={() => {
                      form.setValue("identifier", a.email);
                      form.setValue("password", demo.data!.password);
                    }}
                    className="w-full rounded-lg border px-3 py-2 text-left transition-colors hover:border-primary/50 hover:bg-secondary/50"
                  >
                    <span className="block text-sm font-medium">{t(`roles.${a.role}`)}</span>
                    <span className="block truncate text-xs text-muted-foreground">{a.email}</span>
                  </button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
