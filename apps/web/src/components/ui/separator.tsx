import type * as React from "react";
import { cn } from "@/lib/utils";

export function Separator({ className, vertical = false, ...props }: React.ComponentProps<"div"> & { vertical?: boolean }) {
  return (
    <div
      role="separator"
      aria-orientation={vertical ? "vertical" : "horizontal"}
      className={cn("shrink-0 bg-border", vertical ? "h-full w-px" : "h-px w-full", className)}
      {...props}
    />
  );
}
