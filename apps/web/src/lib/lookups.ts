"use client";

import { localized, useT } from "@/i18n/i18n";
import type { Page } from "@/lib/api";
import { useApi } from "@/lib/query";
import type { UserBrief, Village, WasteStream } from "@/lib/types";

export function useVillages() {
  return useApi<Page<Village>>("/villages", { page_size: 200 }, { staleTime: 5 * 60_000 });
}

export function useStreams() {
  return useApi<WasteStream[]>("/settings/waste-streams", undefined, { staleTime: 5 * 60_000 });
}

export function useAssignable(villageId: string | null | undefined, role: "collector" | "driver" = "collector") {
  return useApi<UserBrief[]>(villageId ? "/users/assignable" : null, { village_id: villageId, role });
}

/** Lookup helpers that turn ids into readable, localised labels. */
export function useLabels() {
  const { locale } = useT();
  const villages = useVillages();
  const streams = useStreams();
  return {
    village: (id: string | null | undefined) => villages.data?.items.find((v) => v.id === id)?.name ?? "—",
    stream: (id: string | null | undefined) => {
      const s = streams.data?.find((x) => x.id === id);
      return s ? localized(s.labels, s.label, locale) : "—";
    },
    streamColor: (id: string | null | undefined) => streams.data?.find((x) => x.id === id)?.color ?? "#94a3b8",
    villages: villages.data?.items ?? [],
    streams: streams.data ?? [],
  };
}
