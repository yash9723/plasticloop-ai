"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/common/error-state";

export default function GlobalRouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <main className="page-container">
      <ErrorState error={error} onRetry={reset} />
    </main>
  );
}
