import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";
import { cn } from "@/lib/utils";

export const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium [&_svg]:size-3",
  {
    variants: {
      tone: {
        neutral: "border-transparent bg-muted text-muted-foreground",
        primary: "border-transparent bg-secondary text-secondary-foreground",
        success: "border-transparent bg-success-soft text-emerald-800 dark:text-emerald-200",
        warning: "border-transparent bg-warning-soft text-warning-foreground",
        danger: "border-transparent bg-danger-soft text-danger-foreground",
        info: "border-transparent bg-info-soft text-info-foreground",
        outline: "border-border text-foreground",
        simulated:
          "border-amber-400/70 bg-[repeating-linear-gradient(135deg,var(--warning-soft)_0_6px,transparent_6px_12px)] text-warning-foreground",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({ className, tone, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ tone }), className)} {...props} />;
}
