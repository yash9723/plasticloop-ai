import { cn } from "@/lib/utils";

/** Loop mark: two arcs chasing each other — material that keeps circulating instead of leaking. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("shrink-0", className)} role="img" aria-label="PlasticLoop AI">
      <rect width="32" height="32" rx="9" fill="#166534" />
      <path d="M9.5 16.5a6.5 6.5 0 0 1 11.2-4.5" fill="none" stroke="#6ee7b7" strokeWidth="2.6" strokeLinecap="round" />
      <path d="m21.6 8.6-.6 3.9-3.8-.9" fill="none" stroke="#6ee7b7" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M22.5 15.5a6.5 6.5 0 0 1-11.2 4.5" fill="none" stroke="#ffffff" strokeWidth="2.6" strokeLinecap="round" />
      <path d="m10.4 23.4.6-3.9 3.8.9" fill="none" stroke="#ffffff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function BrandLockup({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <BrandMark className="size-8" />
      <span className="text-[1.05rem] font-semibold tracking-tight">PlasticLoop AI</span>
    </span>
  );
}
