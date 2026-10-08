import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";
import { cn } from "@/lib/utils";

const alertVariants = cva(
  "relative flex w-full gap-3 rounded-xl border px-4 py-3 text-sm [&>svg]:mt-0.5 [&>svg]:size-4 [&>svg]:shrink-0",
  {
    variants: {
      tone: {
        info: "border-sky-200 bg-info-soft text-info-foreground dark:border-sky-900",
        success: "border-emerald-200 bg-success-soft text-emerald-900 dark:border-emerald-900 dark:text-emerald-100",
        warning: "border-amber-200 bg-warning-soft text-warning-foreground dark:border-amber-900",
        danger: "border-red-200 bg-danger-soft text-danger-foreground dark:border-red-900",
        neutral: "bg-muted text-foreground",
      },
    },
    defaultVariants: { tone: "info" },
  },
);

export function Alert({ className, tone, ...props }: React.ComponentProps<"div"> & VariantProps<typeof alertVariants>) {
  return <div role="status" className={cn(alertVariants({ tone }), className)} {...props} />;
}

export function AlertTitle({ className, ...props }: React.ComponentProps<"p">) {
  return <p className={cn("font-medium leading-tight", className)} {...props} />;
}

export function AlertDescription({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("mt-0.5 text-sm opacity-90", className)} {...props} />;
}
