"use client";

import { AppShell } from "@/components/layout/app-shell";
import { AuthGate } from "@/components/layout/auth-gate";
import { useLiveEvents } from "@/lib/live";
import { useAutoSync } from "@/lib/offline/hooks";

function SyncRunner() {
  useAutoSync();
  useLiveEvents();
  return null;
}

export default function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <SyncRunner />
      <AppShell>{children}</AppShell>
    </AuthGate>
  );
}
