import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import type * as React from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const tones = {
  primary: "bg-secondary text-primary",
  teal: "bg-accent text-accent-foreground",
  warning: "bg-warning-soft text-warning-foreground",
  danger: "bg-danger-soft text-danger-foreground",
  neutral: "bg-muted text-muted-foreground",
};

export function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "primary",
  loading,
  href,
  footer,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: LucideIcon;
  tone?: keyof typeof tones;
  loading?: boolean;
  href?: string;
  footer?: React.ReactNode;
}) {
  const body = (
    <div className="flex h-full flex-col rounded-xl border bg-card p-4 shadow-[var(--shadow-card)] transition-colors sm:p-5 [a:hover>&]:border-primary/40">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        {Icon && (
          <span className={cn("grid size-9 shrink-0 place-items-center rounded-lg", tones[tone])}>
            <Icon className="size-[18px]" aria-hidden />
          </span>
        )}
      </div>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-24" />
      ) : (
        <p className="tabular mt-1 text-2xl font-semibold tracking-tight sm:text-[1.75rem]">{value}</p>
      )}
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
      {footer && <div className="mt-auto pt-3">{footer}</div>}
    </div>
  );
  return href ? (
    <Link href={href} className="block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {body}
    </Link>
  ) : (
    body
  );
}
