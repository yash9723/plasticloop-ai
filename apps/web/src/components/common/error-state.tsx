"use client";

import { AlertTriangle, RotateCw, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n/i18n";
import { ApiError, NetworkError } from "@/lib/api";

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useT();
  const offline = error instanceof NetworkError;
  const Icon = offline ? WifiOff : AlertTriangle;
  const message =
    error instanceof ApiError && error.status === 403
      ? t("errors.forbidden")
      : error instanceof ApiError && error.status === 404
        ? t("errors.notFoundBody")
        : offline
          ? t("errors.offline")
          : error instanceof Error
            ? error.message
            : t("errors.generic");
  return (
    <div role="alert" className="flex flex-col items-center justify-center rounded-xl border border-dashed px-6 py-10 text-center">
      <span className="mb-3 grid size-12 place-items-center rounded-full bg-danger-soft">
        <Icon className="size-6 text-danger-foreground" aria-hidden />
      </span>
      <p className="font-medium">{offline ? t("errors.offlineTitle") : t("errors.title")}</p>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">{message}</p>
      {error instanceof ApiError && error.requestId && (
        <p className="mt-2 font-mono text-[11px] text-muted-foreground">
          {t("errors.reference")}: {error.requestId}
        </p>
      )}
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          <RotateCw /> {t("common.retry")}
        </Button>
      )}
    </div>
  );
}
